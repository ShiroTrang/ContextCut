/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "opvalidator.h"
#include "bin/projectclip.h"
#include "bin/projectitemmodel.h"
#include "bin/model/subtitlemodel.hpp"
#include "core.h"
#include "lib/audio/audioStreamInfo.h"
#include "opregistry.h"
#include "timelineaccess.h"

#include <QRegularExpression>
#include <QSet>
#include <climits>
#include <cmath>
#include <tuple>

namespace ContextCut {

namespace {

constexpr int MaxOps = 200;

const QStringList TextTrackNames{QStringLiteral("chữ"), QStringLiteral("chu"), QStringLiteral("text"), QStringLiteral("title"), QStringLiteral("titles")};
const QStringList MusicTrackNames{QStringLiteral("nhạc"), QStringLiteral("nhac"), QStringLiteral("nhạc/sfx"), QStringLiteral("music"),
                                  QStringLiteral("bgm")};

OpIssue issue(const Op &op, const QString &field, const QString &message)
{
    return {op.index, field, message};
}

QString trackName(const std::shared_ptr<TimelineItemModel> &timeline, int tid)
{
    return timeline->getTrackProperty(tid, QStringLiteral("kdenlive:track_name")).toString().trimmed();
}

QString trackLabel(const std::shared_ptr<TimelineItemModel> &timeline, int tid)
{
    const QString name = trackName(timeline, tid);
    const QString tag = timeline->getTrackTagById(tid);
    return name.isEmpty() ? tag : QStringLiteral("%1 (%2)").arg(tag, name);
}

/** Tracks in display order, top to bottom (as get_timeline lists them). */
QList<int> displayTracks(const std::shared_ptr<TimelineItemModel> &timeline)
{
    const auto ids = timeline->getAllTracksIds();
    QList<int> ordered(ids.begin(), ids.end());
    std::sort(ordered.begin(), ordered.end(), [&timeline](int a, int b) { return timeline->getTrackPosition(a) > timeline->getTrackPosition(b); });
    return ordered;
}

/** First item of @p tid (other than @p ignore) intersecting [start, end), or -1. */
int occupant(const std::shared_ptr<TimelineItemModel> &timeline, int tid, int start, int end, const std::unordered_set<int> &ignore = {})
{
    if (end <= start) {
        return -1;
    }
    for (int id : timeline->getItemsInRange(tid, start, end)) {
        if (ignore.count(id) == 0 && (timeline->isClip(id) || timeline->isComposition(id))) {
            return id;
        }
    }
    return -1;
}

bool checkFree(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, int tid, int start, int end, const QString &field, OpIssue &error,
               const std::unordered_set<int> &ignore = {})
{
    const int other = occupant(timeline, tid, start, end, ignore);
    if (other < 0) {
        return true;
    }
    const int pos = timeline->getItemPosition(other);
    error = issue(op, field,
                  QStringLiteral("%1 already has item %2 at [%3, %4); [%5, %6) must be free")
                      .arg(trackLabel(timeline, tid))
                      .arg(other)
                      .arg(pos)
                      .arg(pos + timeline->getItemPlaytime(other))
                      .arg(start)
                      .arg(end));
    return false;
}

bool checkUnlocked(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, int tid, const QString &field, OpIssue &error)
{
    if (timeline->trackIsLocked(tid)) {
        error = issue(op, field, QStringLiteral("track %1 is locked").arg(trackLabel(timeline, tid)));
        return false;
    }
    return true;
}

bool checkKind(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, int tid, bool audio, const QString &field, OpIssue &error)
{
    if (timeline->isAudioTrack(tid) != audio) {
        error = issue(op, field, QStringLiteral("track %1 is not %2 track").arg(trackLabel(timeline, tid), audio ? QStringLiteral("an audio") : QStringLiteral("a video")));
        return false;
    }
    return true;
}

/** Track named like @p names (top to bottom, unlocked, of the given kind), or -1. */
int namedTrack(const std::shared_ptr<TimelineItemModel> &timeline, const QStringList &names, bool audio)
{
    for (int tid : displayTracks(timeline)) {
        if (timeline->isAudioTrack(tid) == audio && !timeline->trackIsLocked(tid) && names.contains(trackName(timeline, tid).toLower())) {
            return tid;
        }
    }
    return -1;
}

/** Explicit track param, or the default for text/music ops. */
bool resolveOpTrack(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, bool audio, OpIssue &error, QList<OpIssue> &warnings)
{
    if (op.has(QStringLiteral("track"))) {
        op.track = OpValidator::resolveTrack(timeline, op.params.value(QLatin1String("track")), error);
        if (op.track < 0) {
            error.opIndex = op.index;
            return false;
        }
        return checkKind(timeline, op, op.track, audio, QStringLiteral("track"), error) &&
               checkUnlocked(timeline, op, op.track, QStringLiteral("track"), error);
    }
    if (audio) {
        op.track = namedTrack(timeline, MusicTrackNames, true);
        if (op.track < 0) {
            error = issue(op, QStringLiteral("track"), QStringLiteral("no unlocked audio track named Nhạc/Music; pass track (id, tag like \"A2\" or name)"));
            return false;
        }
        return true;
    }
    op.track = namedTrack(timeline, TextTrackNames, false);
    if (op.track >= 0) {
        return true;
    }
    for (int tid : displayTracks(timeline)) {
        if (!timeline->isAudioTrack(tid) && !timeline->trackIsLocked(tid)) {
            op.track = tid;
            warnings << issue(op, QStringLiteral("track"),
                              QStringLiteral("no track named Chữ/Text/Title: using the top unlocked video track %1").arg(trackLabel(timeline, tid)));
            return true;
        }
    }
    error = issue(op, QStringLiteral("track"), QStringLiteral("no unlocked video track"));
    return false;
}

/** Common checks for an existing timeline clip referenced by clip_id. */
bool checkClip(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, OpIssue &error)
{
    const int cid = op.frame(QStringLiteral("clip_id"));
    if (!timeline->isClip(cid) || timeline->getClipTrackId(cid) < 0) {
        error = issue(op, QStringLiteral("clip_id"), QStringLiteral("no clip %1 on the timeline (ids change when the app restarts; read get_timeline)").arg(cid));
        return false;
    }
    return checkUnlocked(timeline, op, timeline->getClipTrackId(cid), QStringLiteral("clip_id"), error);
}

bool checkNoMix(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, OpIssue &error)
{
    for (int cid : OpValidator::groupOf(timeline, op.frame(QStringLiteral("clip_id")))) {
        const int tid = timeline->getClipTrackId(cid);
        const auto track = tid >= 0 ? TimelineAccess::track(*timeline, tid) : nullptr;
        const auto mixes = track ? track->getMixInfo(cid) : std::pair<MixInfo, MixInfo>();
        if (track && (mixes.first.firstClipId > -1 || mixes.second.firstClipId > -1)) {
            error = issue(op, QStringLiteral("clip_id"), QStringLiteral("clip %1 has a same-track transition (mix); %2 does not support mixes yet").arg(cid).arg(op.type));
            return false;
        }
    }
    return true;
}

/** Source exists in the bin, is loaded, is not a sequence; in/out inside it (out defaults to its end). */
bool checkSource(Op &op, bool needVideo, bool needAudio, OpIssue &error, std::shared_ptr<ProjectClip> &clip)
{
    const QString binId = op.string(QStringLiteral("source"));
    clip = OpValidator::sourceClip(binId);
    if (!clip) {
        error = issue(op, QStringLiteral("source"), QStringLiteral("no bin clip with id \"%1\" (see list_sources)").arg(binId));
        return false;
    }
    if (!clip->statusReady()) {
        error = issue(op, QStringLiteral("source"), QStringLiteral("bin clip \"%1\" is not loaded yet (ready: false); retry shortly").arg(binId));
        return false;
    }
    if (clip->clipType() == ClipType::Timeline || clip->clipType() == ClipType::Playlist) {
        error = issue(op, QStringLiteral("source"), QStringLiteral("bin clip \"%1\" is a sequence or playlist; not supported by %2").arg(binId, op.type));
        return false;
    }
    if (needVideo && !clip->hasVideo()) {
        error = issue(op, QStringLiteral("source"), QStringLiteral("bin clip \"%1\" has no picture").arg(binId));
        return false;
    }
    if (needAudio && !clip->hasAudio()) {
        error = issue(op, QStringLiteral("source"), QStringLiteral("bin clip \"%1\" has no audio").arg(binId));
        return false;
    }
    const int in = op.frame(QStringLiteral("in_f"));
    const bool limited = clip->hasLimitedDuration();
    const int length = int(clip->frameDuration());
    op.outF = op.has(QStringLiteral("out_f")) ? op.frame(QStringLiteral("out_f")) : (limited ? length : -1);
    if (op.outF < 0) {
        error = issue(op, QStringLiteral("out_f"), QStringLiteral("bin clip \"%1\" has no fixed length; pass out_f").arg(binId));
        return false;
    }
    if (limited && op.outF > length) {
        error = issue(op, QStringLiteral("out_f"), QStringLiteral("out_f %1 is past the end of \"%2\" (%3 frames)").arg(op.outF).arg(clip->clipName()).arg(length));
        return false;
    }
    if (op.outF <= in) {
        error = issue(op, QStringLiteral("out_f"), QStringLiteral("out_f must be greater than in_f (%1)").arg(in));
        return false;
    }
    return true;
}

bool checkAudioStream(Op &op, const std::shared_ptr<ProjectClip> &clip, OpIssue &error)
{
    const QList<int> streams = clip->audioInfo() ? clip->audioInfo()->streams().keys() : QList<int>();
    if (op.has(QStringLiteral("audio_stream"))) {
        op.audioStream = op.frame(QStringLiteral("audio_stream"));
        if (!streams.contains(op.audioStream)) {
            QStringList known;
            for (int s : streams) {
                known << QString::number(s);
            }
            error = issue(op, QStringLiteral("audio_stream"),
                          QStringLiteral("\"%1\" has no audio stream %2 (streams: %3)").arg(clip->clipName()).arg(op.audioStream).arg(known.join(QLatin1String(", "))));
            return false;
        }
        return true;
    }
    op.audioStream = clip->getProducerIntProperty(QStringLiteral("audio_index"));
    if (op.audioStream < 0 && !streams.isEmpty()) {
        op.audioStream = streams.first();
    }
    return true;
}

bool checkCutRange(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings)
{
    const int end = op.frame(QStringLiteral("end_f"));
    if (end > timeline->duration()) {
        error = issue(op, QStringLiteral("end_f"), QStringLiteral("end_f %1 is past the end of the timeline (%2)").arg(end).arg(timeline->duration()));
        return false;
    }
    QStringList locked;
    for (int tid : displayTracks(timeline)) {
        if (timeline->trackIsLocked(tid)) {
            locked << trackLabel(timeline, tid);
        }
    }
    if (locked.size() == int(timeline->getAllTracksIds().size())) {
        error = issue(op, QStringLiteral("start_f"), QStringLiteral("every track is locked"));
        return false;
    }
    if (!locked.isEmpty()) {
        warnings << issue(op, QString(), QStringLiteral("locked tracks are not cut and fall out of sync: %1").arg(locked.join(QLatin1String(", "))));
    }
    if (timeline->hasSubtitleModel() && timeline->getSubtitleModel()->count() > 0 && timeline->getSubtitleModel()->isLocked()) {
        warnings << issue(op, QString(), QStringLiteral("the subtitle track is locked: its subtitles are not moved and fall out of sync"));
    }
    return true;
}

bool checkAddSubtitles(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error)
{
    if (!timeline->hasSubtitleModel()) {
        return true; // the subtitle track is created when the op runs
    }
    const auto subs = timeline->getSubtitleModel();
    if (subs->isLocked()) {
        error = issue(op, QStringLiteral("items"), QStringLiteral("the subtitle track is locked"));
        return false;
    }
    const int layer = op.frame(QStringLiteral("layer"));
    if (layer > subs->getMaxLayer()) {
        error = issue(op, QStringLiteral("layer"), QStringLiteral("subtitle layer %1 does not exist (layers 0..%2)").arg(layer).arg(subs->getMaxLayer()));
        return false;
    }
    const QJsonArray items = op.params.value(QLatin1String("items")).toArray();
    for (int i = 0; i < items.size(); ++i) {
        const QJsonObject item = items.at(i).toObject();
        const int start = item.value(QLatin1String("start_f")).toInt();
        const int end = item.value(QLatin1String("end_f")).toInt();
        const auto existing = OpValidator::subtitlesIn(timeline, layer, start, end);
        if (!existing.isEmpty()) {
            const SubtitleSpan &other = existing.first();
            error = issue(op, QStringLiteral("items"),
                          QStringLiteral("items[%1] [%2, %3) overlaps subtitle %4 at [%5, %6) on layer %7; clear_subtitles first")
                              .arg(i)
                              .arg(start)
                              .arg(end)
                              .arg(other.id)
                              .arg(other.start)
                              .arg(other.end)
                              .arg(layer));
            return false;
        }
    }
    return true;
}

bool checkClearSubtitles(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings)
{
    if (!timeline->hasSubtitleModel() || timeline->getSubtitleModel()->count() == 0) {
        warnings << issue(op, QString(), QStringLiteral("there are no subtitles to clear"));
        return true;
    }
    if (timeline->getSubtitleModel()->isLocked()) {
        error = issue(op, QStringLiteral("start_f"), QStringLiteral("the subtitle track is locked"));
        return false;
    }
    return true;
}

bool frameValue(const QJsonValue &v)
{
    return v.isDouble() && std::floor(v.toDouble()) == v.toDouble() && v.toDouble() >= 0 && v.toDouble() <= INT_MAX;
}

/** Static checks of add_subtitles items: fields, ranges, no overlap between the items themselves. */
void checkItems(const Op &op, QList<OpIssue> &errors)
{
    const QJsonArray items = op.params.value(QLatin1String("items")).toArray();
    QList<std::tuple<int, int, int>> spans; // start, end, index
    for (int i = 0; i < items.size(); ++i) {
        const QJsonObject item = items.at(i).toObject();
        const QJsonValue start = item.value(QLatin1String("start_f"));
        const QJsonValue end = item.value(QLatin1String("end_f"));
        const QJsonValue text = item.value(QLatin1String("text"));
        const QJsonValue speaker = item.value(QLatin1String("speaker"));
        QString problem;
        if (!items.at(i).isObject()) {
            problem = QStringLiteral("must be an object {start_f, end_f, text, speaker?}");
        } else if (!frameValue(start) || !frameValue(end) || end.toInt() <= start.toInt()) {
            problem = QStringLiteral("needs integer frames start_f >= 0 and end_f > start_f");
        } else if (!text.isString() || text.toString().trimmed().isEmpty() || text.toString().size() > 500) {
            problem = QStringLiteral("text must be a string of 1..500 characters");
        } else if (!speaker.isUndefined() && !speaker.isNull() && (!speaker.isString() || speaker.toString().size() > 60)) {
            problem = QStringLiteral("speaker must be a string of at most 60 characters");
        }
        if (!problem.isEmpty()) {
            errors << issue(op, QStringLiteral("items"), QStringLiteral("items[%1] %2").arg(i).arg(problem));
            return;
        }
        spans << std::make_tuple(start.toInt(), end.toInt(), i);
    }
    std::sort(spans.begin(), spans.end());
    for (int k = 1; k < spans.size(); ++k) {
        if (std::get<0>(spans[k]) < std::get<1>(spans[k - 1])) {
            errors << issue(op, QStringLiteral("items"),
                            QStringLiteral("items[%1] [%2, %3) overlaps items[%4] [%5, %6)")
                                .arg(std::get<2>(spans[k]))
                                .arg(std::get<0>(spans[k]))
                                .arg(std::get<1>(spans[k]))
                                .arg(std::get<2>(spans[k - 1]))
                                .arg(std::get<0>(spans[k - 1]))
                                .arg(std::get<1>(spans[k - 1])));
            return;
        }
    }
}

bool checkSplit(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error)
{
    if (!checkClip(timeline, op, error)) {
        return false;
    }
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int start = timeline->getClipPosition(cid);
    const int end = start + timeline->getClipPlaytime(cid);
    const int at = op.frame(QStringLiteral("at_f"));
    if (at <= start || at >= end) {
        error = issue(op, QStringLiteral("at_f"), QStringLiteral("at_f must be strictly inside clip %1 [%2, %3)").arg(cid).arg(start).arg(end));
        return false;
    }
    return true;
}

bool checkTrim(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error)
{
    if (!checkClip(timeline, op, error) || !checkNoMix(timeline, op, error)) {
        return false;
    }
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int start = timeline->getClipPosition(cid);
    const int end = start + timeline->getClipPlaytime(cid);
    const int newStart = op.has(QStringLiteral("start_f")) ? op.frame(QStringLiteral("start_f")) : start;
    const int newEnd = op.has(QStringLiteral("end_f")) ? op.frame(QStringLiteral("end_f")) : end;
    if (newEnd <= newStart) {
        error = issue(op, QStringLiteral("end_f"), QStringLiteral("the clip would be empty: [%1, %2)").arg(newStart).arg(newEnd));
        return false;
    }
    const int newIn = timeline->getClipIn(cid) + newStart - start;
    if (newIn < 0) {
        error = issue(op, QStringLiteral("start_f"), QStringLiteral("start_f %1 is before the start of the source (earliest %2)").arg(newStart).arg(start - timeline->getClipIn(cid)));
        return false;
    }
    const int maxDuration = ClipAccess::maxDuration(*TimelineAccess::clip(*timeline, cid));
    if (maxDuration > 0 && newIn + newEnd - newStart > maxDuration) {
        error = issue(op, QStringLiteral("end_f"), QStringLiteral("end_f %1 is past the end of the source (latest %2)").arg(newEnd).arg(newStart + maxDuration - newIn));
        return false;
    }
    // Clips of the group sharing an edge follow it (TimelineModel::requestItemResize); the space they grow into must be free
    const std::unordered_set<int> group = OpValidator::groupOf(timeline, cid);
    for (int other : group) {
        const int tid = timeline->getClipTrackId(other);
        const int otherStart = timeline->getClipPosition(other);
        const int otherEnd = otherStart + timeline->getClipPlaytime(other);
        if (otherStart == start && newStart < start && !checkFree(timeline, op, tid, newStart, start, QStringLiteral("start_f"), error, group)) {
            return false;
        }
        if (otherEnd == end && newEnd > end && !checkFree(timeline, op, tid, end, newEnd, QStringLiteral("end_f"), error, group)) {
            return false;
        }
    }
    return true;
}

bool checkMove(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error)
{
    if (!checkClip(timeline, op, error) || !checkNoMix(timeline, op, error)) {
        return false;
    }
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int currentTrack = timeline->getClipTrackId(cid);
    op.track = currentTrack;
    if (op.has(QStringLiteral("track"))) {
        op.track = OpValidator::resolveTrack(timeline, op.params.value(QLatin1String("track")), error);
        if (op.track < 0) {
            error.opIndex = op.index;
            return false;
        }
        if (!checkKind(timeline, op, op.track, timeline->isAudioTrack(currentTrack), QStringLiteral("track"), error) ||
            !checkUnlocked(timeline, op, op.track, QStringLiteral("track"), error)) {
            return false;
        }
    }
    const std::unordered_set<int> group = OpValidator::groupOf(timeline, cid);
    const int delta = op.frame(QStringLiteral("at_f")) - timeline->getClipPosition(cid);
    for (int other : group) {
        const int tid = timeline->getClipTrackId(other);
        if (other != cid && !checkUnlocked(timeline, op, tid, QStringLiteral("clip_id"), error)) {
            return false;
        }
        const int start = timeline->getClipPosition(other) + delta;
        if (start < 0) {
            error = issue(op, QStringLiteral("at_f"), QStringLiteral("clip %1 of the group would start before frame 0").arg(other));
            return false;
        }
        // Grouped clips changing track land where Kdenlive mirrors them; it refuses an occupied spot at apply time
        const int destination = other == cid ? op.track : (op.track == currentTrack ? tid : -1);
        if (destination >= 0 && !checkFree(timeline, op, destination, start, start + timeline->getClipPlaytime(other), QStringLiteral("at_f"), error, group)) {
            return false;
        }
    }
    return true;
}

bool checkInsert(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error)
{
    op.track = OpValidator::resolveTrack(timeline, op.params.value(QLatin1String("track")), error);
    if (op.track < 0) {
        error.opIndex = op.index;
        return false;
    }
    if (!checkUnlocked(timeline, op, op.track, QStringLiteral("track"), error)) {
        return false;
    }
    const bool audioOnly = timeline->isAudioTrack(op.track);
    std::shared_ptr<ProjectClip> clip;
    if (!checkSource(op, !audioOnly, audioOnly, error, clip)) {
        return false;
    }
    const int at = op.frame(QStringLiteral("at_f"));
    const int length = op.outF - op.frame(QStringLiteral("in_f"));
    if (!checkFree(timeline, op, op.track, at, at + length, QStringLiteral("at_f"), error)) {
        return false;
    }
    if (audioOnly) {
        return checkAudioStream(op, clip, error);
    }
    if (!op.flag(QStringLiteral("audio")) || !clip->hasAudio()) {
        return true;
    }
    if (op.has(QStringLiteral("audio_track"))) {
        op.audioTrack = OpValidator::resolveTrack(timeline, op.params.value(QLatin1String("audio_track")), error);
        if (op.audioTrack < 0) {
            error.opIndex = op.index;
            error.field = QStringLiteral("audio_track");
            return false;
        }
    } else {
        op.audioTrack = timeline->getMirrorAudioTrackId(op.track);
        if (op.audioTrack < 0) {
            error = issue(op, QStringLiteral("audio_track"),
                          QStringLiteral("no audio track is paired with %1; pass audio_track, or audio: false").arg(trackLabel(timeline, op.track)));
            return false;
        }
    }
    return checkKind(timeline, op, op.audioTrack, true, QStringLiteral("audio_track"), error) &&
           checkUnlocked(timeline, op, op.audioTrack, QStringLiteral("audio_track"), error) &&
           checkFree(timeline, op, op.audioTrack, at, at + length, QStringLiteral("at_f"), error) && checkAudioStream(op, clip, error);
}

bool checkMusic(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings)
{
    std::shared_ptr<ProjectClip> clip;
    if (!resolveOpTrack(timeline, op, true, error, warnings) || !checkSource(op, false, true, error, clip)) {
        return false;
    }
    const int at = op.frame(QStringLiteral("at_f"));
    return checkFree(timeline, op, op.track, at, at + op.outF - op.frame(QStringLiteral("in_f")), QStringLiteral("at_f"), error) &&
           checkAudioStream(op, clip, error);
}

bool checkText(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings)
{
    return resolveOpTrack(timeline, op, false, error, warnings) &&
           checkFree(timeline, op, op.track, op.frame(QStringLiteral("start_f")), op.frame(QStringLiteral("end_f")), QStringLiteral("start_f"), error);
}

/** Type and range of one param; @p value is present and not null. */
bool checkParamValue(const ParamSpec &spec, const QJsonValue &value, QString &message)
{
    switch (spec.type) {
    case ParamType::Frame:
    case ParamType::Int:
    case ParamType::Clip:
    case ParamType::Number: {
        const double number = value.toDouble(std::nan(""));
        const bool integer = spec.type != ParamType::Number;
        if (!value.isDouble() || (integer && std::floor(number) != number) || number < spec.min || (spec.max > spec.min && number > spec.max)) {
            message = spec.type == ParamType::Clip ? QStringLiteral("%1 must be a clip id (integer)").arg(spec.name)
                                                   : QStringLiteral("%1 must be %2 in %3..%4")
                                                         .arg(spec.name, integer ? QStringLiteral("an integer") : QStringLiteral("a number"))
                                                         .arg(spec.min)
                                                         .arg(spec.max);
            return false;
        }
        return true;
    }
    case ParamType::String:
    case ParamType::Source: {
        const QString text = value.toString();
        if (!value.isString() || text.trimmed().size() < int(spec.min) || (spec.max > 0 && text.size() > int(spec.max)) ||
            (spec.type == ParamType::Source && text.trimmed().isEmpty())) {
            message = spec.type == ParamType::Source ? QStringLiteral("%1 must be a bin clip id string").arg(spec.name)
                                                     : QStringLiteral("%1 must be a string of %2..%3 characters").arg(spec.name).arg(spec.min).arg(spec.max);
            return false;
        }
        return true;
    }
    case ParamType::Enum:
        if (!spec.values.contains(value.toString())) {
            message = QStringLiteral("%1 must be one of %2").arg(spec.name, spec.values.join(QLatin1String(", ")));
            return false;
        }
        return true;
    case ParamType::Bool:
        if (!value.isBool()) {
            message = QStringLiteral("%1 must be true or false").arg(spec.name);
            return false;
        }
        return true;
    case ParamType::Track:
        if (!value.isString() && !(value.isDouble() && std::floor(value.toDouble()) == value.toDouble())) {
            message = QStringLiteral("%1 must be a track id, tag like \"V1\" or track name").arg(spec.name);
            return false;
        }
        return true;
    case ParamType::Items: {
        const int count = value.isArray() ? int(value.toArray().size()) : -1;
        if (count < int(spec.min) || (spec.max > 0 && count > int(spec.max))) {
            message = QStringLiteral("%1 must be an array of %2..%3 items").arg(spec.name).arg(spec.min).arg(spec.max);
            return false;
        }
        return true;
    }
    }
    return true;
}

/** start < end style constraints between two params of one op. */
void checkOrder(const Op &op, const QString &first, const QString &second, QList<OpIssue> &errors)
{
    if (op.has(first) && op.has(second) && op.frame(second) <= op.frame(first)) {
        errors << issue(op, second, QStringLiteral("%1 must be greater than %2 (%3)").arg(second, first).arg(op.frame(first)));
    }
}

} // namespace

QJsonObject OpIssue::toJson() const
{
    QJsonObject obj{{QStringLiteral("op_index"), opIndex}, {QStringLiteral("message"), message}};
    if (!field.isEmpty()) {
        obj.insert(QStringLiteral("field"), field);
    }
    return obj;
}

bool Op::has(const QString &name) const
{
    const QJsonValue value = params.value(name);
    return !value.isUndefined() && !value.isNull();
}

int Op::frame(const QString &name) const
{
    return params.value(name).toInt();
}

double Op::number(const QString &name) const
{
    return params.value(name).toDouble();
}

QString Op::string(const QString &name) const
{
    return params.value(name).toString();
}

bool Op::flag(const QString &name) const
{
    return params.value(name).toBool();
}

namespace OpValidator {

QList<Op> parse(const QJsonValue &ops, QList<OpIssue> &errors, QList<OpIssue> &warnings)
{
    QList<Op> parsed;
    if (!ops.isArray() || ops.toArray().isEmpty() || ops.toArray().size() > MaxOps) {
        errors << OpIssue{-1, QStringLiteral("ops"), QStringLiteral("ops must be an array of 1..%1 operations").arg(MaxOps)};
        return parsed;
    }
    const QJsonArray list = ops.toArray();
    for (int i = 0; i < list.size(); ++i) {
        Op op;
        op.index = i;
        if (!list.at(i).isObject()) {
            errors << OpIssue{i, QStringLiteral("type"), QStringLiteral("each op must be an object with a type")};
            continue;
        }
        op.params = list.at(i).toObject();
        op.type = op.params.value(QLatin1String("type")).toString();
        const OpSpec *spec = OpRegistry::find(op.type);
        if (spec == nullptr) {
            QStringList known;
            for (const OpSpec &s : OpRegistry::specs()) {
                known << s.type;
            }
            errors << issue(op, QStringLiteral("type"), QStringLiteral("unknown op type \"%1\"; known: %2").arg(op.type, known.join(QLatin1String(", "))));
            continue;
        }
        QSet<QString> knownFields{QStringLiteral("type")};
        for (const ParamSpec &param : spec->params) {
            knownFields.insert(param.name);
            if (!op.has(param.name)) {
                if (param.required) {
                    errors << issue(op, param.name, QStringLiteral("%1 is required").arg(param.name));
                } else if (!param.defaultValue.isUndefined()) {
                    op.params.insert(param.name, param.defaultValue);
                }
                continue;
            }
            QString message;
            if (!checkParamValue(param, op.params.value(param.name), message)) {
                errors << issue(op, param.name, message);
            }
        }
        for (auto it = op.params.constBegin(); it != op.params.constEnd(); ++it) {
            if (!knownFields.contains(it.key())) {
                warnings << issue(op, it.key(), QStringLiteral("unknown field \"%1\" ignored (see list_operations)").arg(it.key()));
            }
        }
        checkOrder(op, QStringLiteral("start_f"), QStringLiteral("end_f"), errors);
        checkOrder(op, QStringLiteral("in_f"), QStringLiteral("out_f"), errors);
        if (op.type == QLatin1String("trim") && !op.has(QStringLiteral("start_f")) && !op.has(QStringLiteral("end_f"))) {
            errors << issue(op, QStringLiteral("end_f"), QStringLiteral("trim needs start_f, end_f or both"));
        }
        static const QRegularExpression colour(QStringLiteral("^#[0-9A-Fa-f]{6}$"));
        if (op.has(QStringLiteral("color")) && !colour.match(op.string(QStringLiteral("color"))).hasMatch()) {
            errors << issue(op, QStringLiteral("color"), QStringLiteral("color must look like #FFD400"));
        }
        if (op.type == QLatin1String("add_subtitles") && op.params.value(QLatin1String("items")).isArray()) {
            checkItems(op, errors);
        }
        parsed << op;
    }
    return parsed;
}

bool checkState(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings)
{
    error = OpIssue{op.index, QString(), QString()};
    if (op.type == QLatin1String("cut_range")) {
        return checkCutRange(timeline, op, error, warnings);
    }
    if (op.type == QLatin1String("split")) {
        return checkSplit(timeline, op, error);
    }
    if (op.type == QLatin1String("trim")) {
        return checkTrim(timeline, op, error);
    }
    if (op.type == QLatin1String("move")) {
        return checkMove(timeline, op, error);
    }
    if (op.type == QLatin1String("insert_clip")) {
        return checkInsert(timeline, op, error);
    }
    if (op.type == QLatin1String("add_music")) {
        return checkMusic(timeline, op, error, warnings);
    }
    if (op.type == QLatin1String("title_card") || op.type == QLatin1String("caption")) {
        return checkText(timeline, op, error, warnings);
    }
    if (op.type == QLatin1String("add_subtitles")) {
        return checkAddSubtitles(timeline, op, error);
    }
    if (op.type == QLatin1String("clear_subtitles")) {
        return checkClearSubtitles(timeline, op, error, warnings);
    }
    error = issue(op, QStringLiteral("type"), QStringLiteral("no state check for %1").arg(op.type));
    return false;
}

int resolveTrack(const std::shared_ptr<TimelineItemModel> &timeline, const QJsonValue &ref, OpIssue &error)
{
    const QList<int> tracks = displayTracks(timeline);
    error.field = QStringLiteral("track");
    if (ref.isDouble()) {
        const int tid = ref.toInt(-1);
        if (tracks.contains(tid)) {
            return tid;
        }
        error.message = QStringLiteral("no track with id %1").arg(ref.toDouble());
        return -1;
    }
    const QString wanted = ref.toString().trimmed();
    for (int tid : tracks) {
        if (timeline->getTrackTagById(tid).compare(wanted, Qt::CaseInsensitive) == 0) {
            return tid;
        }
    }
    QList<int> named;
    for (int tid : tracks) {
        if (trackName(timeline, tid).compare(wanted, Qt::CaseInsensitive) == 0) {
            named << tid;
        }
    }
    if (named.size() == 1) {
        return named.first();
    }
    QStringList known;
    for (int tid : tracks) {
        known << trackLabel(timeline, tid);
    }
    error.message = named.isEmpty() ? QStringLiteral("no track \"%1\"; tracks: %2").arg(wanted, known.join(QLatin1String(", ")))
                                    : QStringLiteral("several tracks are named \"%1\"; use the tag").arg(wanted);
    return -1;
}

int groupRoot(const std::shared_ptr<TimelineItemModel> &timeline, int clipId)
{
    GroupsModel &groups = TimelineAccess::groups(*timeline);
    int root = -1;
    for (int parent = groups.getDirectAncestor(clipId); parent != -1; parent = groups.getDirectAncestor(parent)) {
        if (groups.getType(parent) == GroupType::Selection) {
            break;
        }
        root = parent;
    }
    return root;
}

std::unordered_set<int> groupOf(const std::shared_ptr<TimelineItemModel> &timeline, int clipId)
{
    const int root = groupRoot(timeline, clipId);
    if (root < 0) {
        return {clipId};
    }
    std::unordered_set<int> clips;
    for (int id : TimelineAccess::groups(*timeline).getLeaves(root)) {
        if (timeline->isClip(id)) {
            clips.insert(id);
        }
    }
    return clips;
}

QList<SubtitleSpan> subtitlesIn(const std::shared_ptr<TimelineItemModel> &timeline, int layer, int start, int end)
{
    QList<SubtitleSpan> found;
    if (!timeline->hasSubtitleModel()) {
        return found;
    }
    const auto subs = timeline->getSubtitleModel();
    const double fps = pCore->getCurrentFps();
    for (const auto &entry : subs->getAllSubtitles()) {
        const int s = entry.first.second.frames(fps);
        const int e = entry.second.endTime().frames(fps);
        if ((layer < 0 || entry.first.first == layer) && s < end && e > start) {
            found << SubtitleSpan{subs->getIdForStartPos(entry.first.first, entry.first.second), entry.first.first, s, e};
        }
    }
    std::sort(found.begin(), found.end(), [](const SubtitleSpan &a, const SubtitleSpan &b) { return std::tie(a.start, a.layer) < std::tie(b.start, b.layer); });
    return found;
}

std::shared_ptr<ProjectClip> sourceClip(const QString &binId)
{
    const auto model = pCore->projectItemModel();
    return model && model->hasClip(binId) ? model->getClipByBinID(binId) : nullptr;
}

} // namespace OpValidator

} // namespace ContextCut
