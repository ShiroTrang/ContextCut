/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "editorreader.h"
#include "assets/model/assetparametermodel.hpp"
#include "bin/model/markerlistmodel.hpp"
#include "bin/model/subtitlemodel.hpp"
#include "bin/projectclip.h"
#include "bin/projectitemmodel.h"
#include "contextcut/bridge/aibridgeserver.h"
#include "contextcut/bridge/revisiontracker.h"
#include "contextcut/ops/opvalidator.h"
#include "core.h"
#include "doc/docundostack.hpp"
#include "doc/kdenlivedoc.h"
#include "effects/effectstack/model/effectstackmodel.hpp"
#include "lib/audio/audioStreamInfo.h"
#include "mainwindow.h"
#include "timeline2/model/timelineitemmodel.hpp"
#include "timeline2/view/timelinecontroller.h"
#include "timeline2/view/timelinewidget.h"
#include "transitions/transitionsrepository.hpp"

#include <QFileInfo>
#include <QHash>
#include <QRegularExpression>
#include <QSet>
#include <algorithm>
#include <mlt++/MltTractor.h>
#include <climits>
#include <tuple>

namespace ContextCut::EditorReader {

namespace {

constexpr qint64 TimelinePageDefault = 200;
constexpr qint64 TimelinePageMax = 1000;
constexpr qint64 RecordingPageDefault = 100;
constexpr qint64 RecordingPageMax = 500;
constexpr int GuidesMax = 1000;
constexpr qint64 SubtitlePageDefault = 200;
constexpr qint64 SubtitlePageMax = 1000;

QJsonValue nullIfEmpty(const QString &text)
{
    return text.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(text);
}

QJsonObject fpsObject()
{
    const auto [num, den] = pCore->getProjectFpsInfo();
    return {{QStringLiteral("num"), num}, {QStringLiteral("den"), den}};
}

QString clipTypeName(ClipType::ProducerType type)
{
    switch (type) {
    case ClipType::Audio:
        return QStringLiteral("audio");
    case ClipType::Video:
        return QStringLiteral("video");
    case ClipType::AV:
        return QStringLiteral("av");
    case ClipType::Color:
        return QStringLiteral("color");
    case ClipType::Image:
        return QStringLiteral("image");
    case ClipType::Text:
    case ClipType::TextTemplate:
    case ClipType::QText:
        return QStringLiteral("title");
    case ClipType::SlideShow:
        return QStringLiteral("slideshow");
    case ClipType::Playlist:
        return QStringLiteral("playlist");
    case ClipType::Timeline:
        return QStringLiteral("sequence");
    case ClipType::Animation:
        return QStringLiteral("animation");
    default:
        return QStringLiteral("other");
    }
}

/** A recording is a bin clip with picture coming from a file (docs/protocol.md §8.4). */
bool isRecording(ClipType::ProducerType type)
{
    return type == ClipType::AV || type == ClipType::Video;
}

/** Kdenlive is still loading the clip. ClipController's constructor takes the producer lock for writing on the GUI thread and
    only setProducer() or setInvalid(), which ClipLoadTask queues back to the GUI thread, release it, so any getter that
    read-locks it (duration, fps, frame size, int properties) would block the GUI thread for good. Leave those fields out,
    as ProjectClip::hash() does for StatusWaiting. */
bool stillLoading(const std::shared_ptr<ProjectClip> &clip)
{
    return clip->clipStatus() == FileStatus::StatusWaiting;
}

QList<int> orderedTrackIds(const std::shared_ptr<TimelineItemModel> &timeline)
{
    const auto ids = timeline->getAllTracksIds();
    QList<int> ordered(ids.begin(), ids.end());
    // Display order is top to bottom, i.e. decreasing position in the MLT tractor (V2, V1, A1, A2)
    std::sort(ordered.begin(), ordered.end(), [&timeline](int a, int b) { return timeline->getTrackPosition(a) > timeline->getTrackPosition(b); });
    return ordered;
}

QJsonObject trackObject(const std::shared_ptr<TimelineItemModel> &timeline, int tid)
{
    // MLT "hide": bit 1 = no video, bit 2 = no audio. Kdenlive always sets the bit a track does not carry (audio tracks
    // hide video, video tracks hide audio), so only the track's own kind is meaningful (as in TimelineItemModel::IsDisabledRole)
    const int hide = timeline->getTrackProperty(tid, QStringLiteral("hide")).toInt();
    const bool audio = timeline->isAudioTrack(tid);
    return {{QStringLiteral("id"), tid},
            {QStringLiteral("tag"), timeline->getTrackTagById(tid)},
            {QStringLiteral("name"), timeline->getTrackProperty(tid, QStringLiteral("kdenlive:track_name")).toString()},
            {QStringLiteral("kind"), audio ? QStringLiteral("audio") : QStringLiteral("video")},
            {QStringLiteral("locked"), timeline->getTrackProperty(tid, QStringLiteral("kdenlive:locked_track")).toInt() != 0},
            {QStringLiteral("hidden"), !audio && (hide & 1) != 0},
            {QStringLiteral("muted"), audio && (hide & 2) != 0},
            {QStringLiteral("items"), timeline->getTrackClipsCount(tid) + timeline->getTrackCompositionsCount(tid)}};
}

QString sequenceName(const std::shared_ptr<TimelineItemModel> &timeline)
{
    return QString::fromUtf8(timeline->tractor()->get("kdenlive:clipname"));
}

QJsonObject sequenceObject(const std::shared_ptr<TimelineItemModel> &timeline)
{
    return {{QStringLiteral("uuid"), timeline->uuid().toString()},
            {QStringLiteral("name"), sequenceName(timeline)},
            {QStringLiteral("duration_f"), timeline->duration()}};
}

QList<std::shared_ptr<ProjectClip>> recordingClips()
{
    QList<std::shared_ptr<ProjectClip>> clips;
    const auto model = pCore->projectItemModel();
    for (const QString &binId : model->getAllClipIds()) {
        auto clip = model->getClipByBinID(binId);
        if (clip && isRecording(clip->clipType())) {
            clips << clip;
        }
    }
    std::sort(clips.begin(), clips.end(), [](const auto &a, const auto &b) { return a->clipId().toInt() < b->clipId().toInt(); });
    return clips;
}

/** Reads limit/cursor (cursor = "<revision>.<offset>", docs/protocol.md §7). */
bool readPage(const QJsonObject &params, qint64 revision, qint64 defaultLimit, qint64 maxLimit, qint64 &offset, qint64 &limit, JsonRpc::RpcError &error)
{
    limit = defaultLimit;
    if (!JsonRpc::optionalInt(params, QStringLiteral("limit"), 1, maxLimit, limit, error)) {
        return false;
    }
    offset = 0;
    const QJsonValue cursor = params.value(QLatin1String("cursor"));
    if (cursor.isUndefined() || cursor.isNull()) {
        return true;
    }
    if (!cursor.isString()) {
        error = JsonRpc::invalidParams(QStringLiteral("cursor"), QStringLiteral("cursor must be a string returned as next_cursor"));
        return false;
    }
    const QStringList parts = cursor.toString().split(QLatin1Char('.'));
    bool revOk = false;
    bool offsetOk = false;
    if (parts.size() == 2) {
        const qint64 cursorRevision = parts.at(0).toLongLong(&revOk);
        offset = parts.at(1).toLongLong(&offsetOk);
        revOk = revOk && cursorRevision == revision;
    }
    if (!revOk || !offsetOk || offset < 0) {
        error = JsonRpc::staleCursor(revision);
        return false;
    }
    return true;
}

QJsonValue nextCursor(qint64 revision, qint64 offset, qint64 limit, qint64 total)
{
    if (offset + limit >= total) {
        return QJsonValue(QJsonValue::Null);
    }
    return QStringLiteral("%1.%2").arg(revision).arg(offset + limit);
}

QJsonObject clipObject(const std::shared_ptr<TimelineItemModel> &timeline, int cid, int tid)
{
    const int position = timeline->getClipPosition(cid);
    const int playtime = timeline->getClipPlaytime(cid);
    const int in = timeline->getClipIn(cid);
    const int partner = timeline->getClipSplitPartner(cid);
    QJsonArray effects;
    if (const auto stack = timeline->getClipEffectStackModel(cid)) {
        for (const QString &name : stack->effectNames().split(QLatin1Char('/'), Qt::SkipEmptyParts)) {
            effects.append(name);
        }
    }
    return {{QStringLiteral("id"), cid},
            {QStringLiteral("kind"), QStringLiteral("clip")},
            {QStringLiteral("track"), tid},
            {QStringLiteral("start_f"), position},
            {QStringLiteral("end_f"), position + playtime},
            {QStringLiteral("source"), timeline->getClipBinId(cid)},
            {QStringLiteral("src_in_f"), in},
            {QStringLiteral("src_out_f"), in + playtime},
            {QStringLiteral("name"), timeline->getClipName(cid)},
            {QStringLiteral("speed"), timeline->getClipSpeed(cid)},
            {QStringLiteral("enabled"), timeline->getClipState(cid).first != PlaylistState::Disabled},
            {QStringLiteral("content"), timeline->isAudioTrack(tid) ? QStringLiteral("audio") : QStringLiteral("video")},
            {QStringLiteral("linked"), partner >= 0 ? QJsonValue(partner) : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("effects"), effects}};
}

QJsonObject compositionObject(const std::shared_ptr<TimelineItemModel> &timeline, int id, int tid)
{
    const int position = timeline->getCompositionPosition(id);
    const auto parameters = timeline->getCompositionParameterModel(id);
    const QString asset = parameters ? parameters->getAssetId() : QString();
    const QString name = TransitionsRepository::get()->exists(asset) ? TransitionsRepository::get()->getName(asset) : asset;
    return {{QStringLiteral("id"), id},
            {QStringLiteral("kind"), QStringLiteral("composition")},
            {QStringLiteral("track"), tid},
            {QStringLiteral("start_f"), position},
            {QStringLiteral("end_f"), position + timeline->getCompositionPlaytime(id)},
            {QStringLiteral("name"), name},
            {QStringLiteral("asset"), asset}};
}

} // namespace

std::shared_ptr<TimelineItemModel> currentTimeline()
{
    if (!pCore->guiReady() || pCore->window() == nullptr) {
        return nullptr;
    }
    TimelineWidget *widget = pCore->window()->getCurrentTimeline();
    return widget ? widget->model() : nullptr;
}

std::shared_ptr<TimelineItemModel> activeTimeline(JsonRpc::RpcError &error)
{
    if (!pCore->guiReady()) {
        error = JsonRpc::busy();
        return nullptr;
    }
    KdenliveDoc *doc = pCore->currentDoc();
    if (doc == nullptr) {
        error = JsonRpc::noProject();
        return nullptr;
    }
    if (doc->isBusy()) {
        error = JsonRpc::busy();
        return nullptr;
    }
    auto timeline = currentTimeline();
    if (!timeline) {
        error = JsonRpc::noProject();
    }
    return timeline;
}

QString undoLabel(const QString &text)
{
    static const QRegularExpression time(QStringLiteral("^\\d\\d:\\d\\d "));
    return QString(text).remove(time);
}

QJsonArray tracks(const std::shared_ptr<TimelineItemModel> &timeline)
{
    QJsonArray list;
    for (int tid : orderedTrackIds(timeline)) {
        list.append(trackObject(timeline, tid));
    }
    return list;
}

JsonRpc::RpcResult editorState(qint64 revision, const QString &session)
{
    JsonRpc::RpcError error;
    const auto timeline = activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    KdenliveDoc *doc = pCore->currentDoc();
    const QString path = doc->url().toLocalFile();
    QJsonObject project{{QStringLiteral("path"), nullIfEmpty(path)}, {QStringLiteral("modified"), doc->isModified()}};
    if (path.isEmpty()) {
        project.insert(QStringLiteral("name"), doc->projectName());
        project.insert(QStringLiteral("companion_dir"), QJsonValue(QJsonValue::Null));
    } else {
        const QFileInfo info(path);
        project.insert(QStringLiteral("name"), info.completeBaseName());
        project.insert(QStringLiteral("companion_dir"), QString(info.absolutePath() + QLatin1Char('/') + info.completeBaseName() + QStringLiteral(".contextcut")));
    }

    const QSize frameSize = pCore->getCurrentFrameSize();
    QJsonArray sequences;
    for (const QUuid &uuid : doc->getTimelinesUuids()) {
        if (const auto sequence = doc->getTimeline(uuid, true)) {
            sequences.append(QJsonObject{{QStringLiteral("uuid"), uuid.toString()},
                                         {QStringLiteral("name"), sequenceName(sequence)},
                                         {QStringLiteral("active"), uuid == timeline->uuid()}});
        }
    }

    const auto selected = timeline->getCurrentSelection();
    QList<int> selectedIds(selected.begin(), selected.end());
    std::sort(selectedIds.begin(), selectedIds.end());
    QJsonArray selection;
    for (int id : std::as_const(selectedIds)) {
        selection.append(id);
    }
    QJsonValue zone(QJsonValue::Null);
    TimelineController *controller = pCore->window()->getCurrentTimeline()->controller();
    if (controller->zoneOut() > controller->zoneIn()) {
        zone = QJsonObject{{QStringLiteral("start_f"), controller->zoneIn()}, {QStringLiteral("end_f"), controller->zoneOut()}};
    }

    const auto guides = timeline->getGuideModel();
    const int subtitles = timeline->hasSubtitleModel() ? timeline->getSubtitleModel()->count() : 0;
    const QJsonObject counts{{QStringLiteral("clips"), timeline->getClipsCount()},
                             {QStringLiteral("compositions"), timeline->getCompositionsCount()},
                             {QStringLiteral("guides"), guides ? guides->rowCount() : 0},
                             {QStringLiteral("subtitles"), subtitles},
                             {QStringLiteral("recordings"), int(recordingClips().size())}};
    const auto undoStack = doc->commandStack();
    const QJsonObject undo{{QStringLiteral("index"), undoStack->index()},
                           {QStringLiteral("count"), undoStack->count()},
                           {QStringLiteral("next_undo"), undoStack->canUndo() ? QJsonValue(undoLabel(undoStack->undoText())) : QJsonValue(QJsonValue::Null)},
                           {QStringLiteral("next_redo"), undoStack->canRedo() ? QJsonValue(undoLabel(undoStack->redoText())) : QJsonValue(QJsonValue::Null)}};

    return JsonRpc::RpcResult::ok(QJsonObject{
        {QStringLiteral("session"), session},
        {QStringLiteral("revision"), revision},
        {QStringLiteral("project"), project},
        {QStringLiteral("profile"),
         QJsonObject{{QStringLiteral("fps"), fpsObject()}, {QStringLiteral("width"), frameSize.width()}, {QStringLiteral("height"), frameSize.height()}}},
        {QStringLiteral("sequence"), sequenceObject(timeline)},
        {QStringLiteral("sequences"), sequences},
        {QStringLiteral("playhead_f"), pCore->getMonitorPosition()},
        {QStringLiteral("selection"), QJsonObject{{QStringLiteral("items"), selection}, {QStringLiteral("zone"), zone}}},
        {QStringLiteral("tracks"), tracks(timeline)},
        {QStringLiteral("counts"), counts},
        {QStringLiteral("undo"), undo},
    });
}

JsonRpc::RpcResult timelinePage(const QJsonObject &params, qint64 revision)
{
    JsonRpc::RpcError error;
    const auto timeline = activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 start = 0;
    qint64 end = -1;
    qint64 offset = 0;
    qint64 limit = 0;
    if (!JsonRpc::optionalInt(params, QStringLiteral("start_f"), 0, INT_MAX, start, error) ||
        !JsonRpc::optionalInt(params, QStringLiteral("end_f"), 1, INT_MAX, end, error) ||
        !readPage(params, revision, TimelinePageDefault, TimelinePageMax, offset, limit, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    if (end < 0) {
        end = std::max<qint64>(timeline->duration(), start);
    } else if (end <= start) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("end_f"), QStringLiteral("end_f must be greater than start_f")));
    }

    const QList<int> trackIds = orderedTrackIds(timeline);
    QHash<int, int> displayIndex;
    QHash<QString, int> byTag;
    for (int i = 0; i < trackIds.size(); ++i) {
        displayIndex.insert(trackIds.at(i), i);
        byTag.insert(timeline->getTrackTagById(trackIds.at(i)).toUpper(), trackIds.at(i));
    }
    QList<int> wanted = trackIds;
    const QJsonValue filter = params.value(QLatin1String("tracks"));
    if (!filter.isUndefined() && !filter.isNull()) {
        if (!filter.isArray()) {
            return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("tracks"), QStringLiteral("tracks must be an array of track ids or tags")));
        }
        wanted.clear();
        for (const QJsonValue &entry : filter.toArray()) {
            const int tid = entry.isString() ? byTag.value(entry.toString().toUpper(), -1) : (entry.isDouble() ? entry.toInt(-1) : -1);
            if (!displayIndex.contains(tid)) {
                return JsonRpc::RpcResult::fail(JsonRpc::notFound(entry, QStringLiteral("no such track")));
            }
            wanted << tid;
        }
    }

    struct Entry
    {
        int start;
        int trackIndex;
        int id;
        int track;
    };
    std::vector<Entry> entries;
    for (int tid : std::as_const(wanted)) {
        for (int id : timeline->getItemsInRange(tid, int(start), int(end))) {
            int position = 0;
            int playtime = 0;
            if (timeline->isClip(id)) {
                position = timeline->getClipPosition(id);
                playtime = timeline->getClipPlaytime(id);
            } else if (timeline->isComposition(id)) {
                position = timeline->getCompositionPosition(id);
                playtime = timeline->getCompositionPlaytime(id);
            } else {
                continue;
            }
            if (position < end && position + playtime > start) {
                entries.push_back({position, displayIndex.value(tid), id, tid});
            }
        }
    }
    std::sort(entries.begin(), entries.end(), [](const Entry &a, const Entry &b) {
        return std::tie(a.start, a.trackIndex, a.id) < std::tie(b.start, b.trackIndex, b.id);
    });
    const qint64 total = qint64(entries.size());
    if (offset > total) {
        return JsonRpc::RpcResult::fail(JsonRpc::staleCursor(revision));
    }

    QJsonArray items;
    QSet<QString> binIds;
    for (qint64 i = offset; i < std::min(total, offset + limit); ++i) {
        const Entry &entry = entries.at(size_t(i));
        if (timeline->isClip(entry.id)) {
            binIds.insert(timeline->getClipBinId(entry.id));
            items.append(clipObject(timeline, entry.id, entry.track));
        } else {
            items.append(compositionObject(timeline, entry.id, entry.track));
        }
    }

    QJsonArray guides;
    bool guidesTruncated = false;
    if (const auto guideModel = timeline->getGuideModel()) {
        const double fps = pCore->getCurrentFps();
        // getMarkersInRange takes an inclusive end
        for (const CommentedTime &marker : guideModel->getMarkersInRange(int(start), int(end) - 1)) {
            if (guides.size() >= GuidesMax) {
                guidesTruncated = true;
                break;
            }
            guides.append(QJsonObject{{QStringLiteral("f"), marker.time().frames(fps)},
                                      {QStringLiteral("comment"), marker.comment()},
                                      {QStringLiteral("category"), marker.markerType()}});
        }
    }

    QJsonObject sources;
    for (const QString &binId : std::as_const(binIds)) {
        if (const auto clip = pCore->projectItemModel()->getClipByBinID(binId)) {
            sources.insert(binId, QJsonObject{{QStringLiteral("name"), clip->clipName()},
                                              {QStringLiteral("type"), clipTypeName(clip->clipType())},
                                              {QStringLiteral("recording"), isRecording(clip->clipType())}});
        }
    }

    QJsonObject result{{QStringLiteral("revision"), revision},
                       {QStringLiteral("sequence"), sequenceObject(timeline)},
                       {QStringLiteral("fps"), fpsObject()},
                       {QStringLiteral("range"), QJsonObject{{QStringLiteral("start_f"), start}, {QStringLiteral("end_f"), end}}},
                       {QStringLiteral("tracks"), tracks(timeline)},
                       {QStringLiteral("items"), items},
                       {QStringLiteral("guides"), guides},
                       {QStringLiteral("sources"), sources},
                       {QStringLiteral("next_cursor"), nextCursor(revision, offset, limit, total)}};
    if (guidesTruncated) {
        result.insert(QStringLiteral("guides_truncated"), true);
    }
    return JsonRpc::RpcResult::ok(result);
}

JsonRpc::RpcResult recordings(const QJsonObject &params, qint64 revision)
{
    JsonRpc::RpcError error;
    if (!activeTimeline(error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 offset = 0;
    qint64 limit = 0;
    if (!readPage(params, revision, RecordingPageDefault, RecordingPageMax, offset, limit, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const auto clips = recordingClips();
    const qint64 total = clips.size();
    if (offset > total) {
        return JsonRpc::RpcResult::fail(JsonRpc::staleCursor(revision));
    }
    QJsonArray list;
    for (qint64 i = offset; i < std::min(total, offset + limit); ++i) {
        const auto &clip = clips.at(i);
        QJsonArray streams;
        if (const auto &info = clip->audioInfo()) {
            const QMap<int, QString> names = info->streams();
            const QMap<int, int> channels = info->streamChannels();
            for (auto it = names.cbegin(); it != names.cend(); ++it) {
                // Kdenlive's generated description is "<n>|Mono 48kHz aac"; drop the "<n>|" ordinal
                QString name = it.value();
                name.remove(QRegularExpression(QStringLiteral("^\\d+\\|")));
                streams.append(QJsonObject{{QStringLiteral("index"), it.key()},
                                           {QStringLiteral("name"), name},
                                           {QStringLiteral("channels"), channels.value(it.key(), 0)}});
            }
        }
        const bool loading = stillLoading(clip);
        const QSize size = loading ? QSize() : clip->getFrameSize();
        list.append(QJsonObject{
            {QStringLiteral("id"), clip->clipId()},
            {QStringLiteral("name"), clip->clipName()},
            {QStringLiteral("path"), nullIfEmpty(clip->url())},
            {QStringLiteral("file_hash"), nullIfEmpty(clip->hash())},
            {QStringLiteral("type"), clipTypeName(clip->clipType())},
            {QStringLiteral("ready"), clip->statusReady()},
            {QStringLiteral("duration_f"), loading ? QJsonValue(QJsonValue::Null) : QJsonValue(qint64(clip->frameDuration()))},
            {QStringLiteral("source_fps"), loading ? QJsonValue(QJsonValue::Null) : QJsonValue(clip->getOriginalFps())},
            {QStringLiteral("width"), size.isValid() ? QJsonValue(size.width()) : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("height"), size.isValid() ? QJsonValue(size.height()) : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("audio_streams"), streams},
            {QStringLiteral("on_timeline"), clip->isIncludedInTimeline()},
            {QStringLiteral("track_map"), QJsonValue(QJsonValue::Null)},
            {QStringLiteral("day_start"), QJsonValue(QJsonValue::Null)},
        });
    }
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("revision"), revision},
                                              {QStringLiteral("recordings"), list},
                                              {QStringLiteral("next_cursor"), nextCursor(revision, offset, limit, total)}});
}

QJsonObject sourceObject(const std::shared_ptr<ProjectClip> &clip)
{
    return {{QStringLiteral("id"), clip->clipId()},
            {QStringLiteral("name"), clip->clipName()},
            {QStringLiteral("type"), clipTypeName(clip->clipType())},
            {QStringLiteral("path"), nullIfEmpty(clip->url())},
            {QStringLiteral("duration_f"),
             !stillLoading(clip) && clip->hasLimitedDuration() ? QJsonValue(qint64(clip->frameDuration())) : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("has_video"), clip->hasVideo()},
            {QStringLiteral("has_audio"), clip->hasAudio()},
            {QStringLiteral("ready"), clip->statusReady()},
            {QStringLiteral("on_timeline"), clip->isIncludedInTimeline()},
            {QStringLiteral("recording"), isRecording(clip->clipType())}};
}

JsonRpc::RpcResult sources(const QJsonObject &params, qint64 revision)
{
    JsonRpc::RpcError error;
    if (!activeTimeline(error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 offset = 0;
    qint64 limit = 0;
    if (!readPage(params, revision, RecordingPageDefault, RecordingPageMax, offset, limit, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const auto model = pCore->projectItemModel();
    QList<std::shared_ptr<ProjectClip>> clips;
    for (const QString &binId : model->getAllClipIds()) {
        if (auto clip = model->getClipByBinID(binId)) {
            clips << clip;
        }
    }
    std::sort(clips.begin(), clips.end(), [](const auto &a, const auto &b) { return a->clipId().toInt() < b->clipId().toInt(); });
    const qint64 total = clips.size();
    if (offset > total) {
        return JsonRpc::RpcResult::fail(JsonRpc::staleCursor(revision));
    }
    QJsonArray list;
    for (qint64 i = offset; i < std::min(total, offset + limit); ++i) {
        list.append(sourceObject(clips.at(i)));
    }
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("revision"), revision},
                                              {QStringLiteral("sources"), list},
                                              {QStringLiteral("next_cursor"), nextCursor(revision, offset, limit, total)}});
}

JsonRpc::RpcResult subtitles(const QJsonObject &params, qint64 revision)
{
    JsonRpc::RpcError error;
    const auto timeline = activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 start = 0;
    qint64 end = INT_MAX;
    qint64 offset = 0;
    qint64 limit = 0;
    if (!JsonRpc::optionalInt(params, QStringLiteral("start_f"), 0, INT_MAX, start, error) ||
        !JsonRpc::optionalInt(params, QStringLiteral("end_f"), 1, INT_MAX, end, error) ||
        !readPage(params, revision, SubtitlePageDefault, SubtitlePageMax, offset, limit, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    if (end <= start) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("end_f"), QStringLiteral("end_f must be greater than start_f")));
    }
    const QList<SubtitleSpan> spans = OpValidator::subtitlesIn(timeline, -1, int(start), int(end));
    const qint64 total = spans.size();
    if (offset > total) {
        return JsonRpc::RpcResult::fail(JsonRpc::staleCursor(revision));
    }
    const auto subs = timeline->hasSubtitleModel() ? timeline->getSubtitleModel() : nullptr;
    QJsonArray items;
    for (qint64 i = offset; i < std::min(total, offset + limit); ++i) {
        const SubtitleSpan &s = spans.at(i);
        items.append(QJsonObject{{QStringLiteral("id"), s.id},
                                 {QStringLiteral("layer"), s.layer},
                                 {QStringLiteral("start_f"), s.start},
                                 {QStringLiteral("end_f"), s.end},
                                 {QStringLiteral("text"), subs->getText(s.id)},
                                 {QStringLiteral("speaker"), subs->getName(s.id)}});
    }
    const QJsonObject track{{QStringLiteral("exists"), subs != nullptr},
                            {QStringLiteral("locked"), subs ? subs->isLocked() : false},
                            {QStringLiteral("disabled"), subs ? subs->isDisabled() : false},
                            {QStringLiteral("layers"), subs ? subs->getMaxLayer() + 1 : 0}};
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("revision"), revision},
                                              {QStringLiteral("track"), track},
                                              {QStringLiteral("items"), items},
                                              {QStringLiteral("next_cursor"), nextCursor(revision, offset, limit, total)}});
}

void registerReadOnlyMethods(AiBridgeServer &server)
{
    AiBridgeServer *bridge = &server;
    server.registerMethod(QStringLiteral("get_editor_state"),
                          [bridge](const QJsonObject &) { return editorState(bridge->revisions()->current(), bridge->session()); });
    server.registerMethod(QStringLiteral("get_timeline"), [bridge](const QJsonObject &params) { return timelinePage(params, bridge->revisions()->current()); });
    server.registerMethod(QStringLiteral("list_recordings"),
                          [bridge](const QJsonObject &params) { return recordings(params, bridge->revisions()->current()); });
    server.registerMethod(QStringLiteral("list_sources"), [bridge](const QJsonObject &params) { return sources(params, bridge->revisions()->current()); });
    server.registerMethod(QStringLiteral("list_subtitles"),
                          [bridge](const QJsonObject &params) { return subtitles(params, bridge->revisions()->current()); });
}

} // namespace ContextCut::EditorReader
