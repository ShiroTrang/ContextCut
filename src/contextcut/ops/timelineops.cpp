/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "timelineops.h"
#include "bin/model/markerlistmodel.hpp"
#include "core.h"
#include "effects/effectstack/model/effectstackmodel.hpp"
#include "kdenlivesettings.h"
#include "timelineaccess.h"
#include "timeline2/model/timelinefunctions.hpp"
#include "titleclip.h"

#include <QDomDocument>
#include <QHash>
#include <QPoint>
#include <QVector>

namespace ContextCut::TimelineOps {

namespace {

constexpr int TitleNameLength = 40;

bool fail(OpOutcome &outcome, const QString &field, const QString &error)
{
    outcome.field = field;
    outcome.error = error;
    return false;
}

QList<int> trackIdsTopDown(const std::shared_ptr<TimelineItemModel> &timeline)
{
    const auto ids = timeline->getAllTracksIds();
    QList<int> ordered(ids.begin(), ids.end());
    std::sort(ordered.begin(), ordered.end(), [&timeline](int a, int b) { return timeline->getTrackPosition(a) > timeline->getTrackPosition(b); });
    return ordered;
}

/** A timeline clip of bin clip @p binId frames [in, out) on @p trackId at @p position (requestClipInsertion without its dialogs). */
bool placeClip(const std::shared_ptr<TimelineItemModel> &timeline, const QString &binId, int in, int out, PlaylistState::ClipState state, int audioStream,
               int trackId, int position, Fun &undo, Fun &redo, int &clipId)
{
    const QString zone = QStringLiteral("%1/%2/%3").arg(binId).arg(in).arg(out - 1); // out is inclusive in Kdenlive's "id/in/out"
    return step(undo, redo, [&](Fun &u, Fun &r) { return TimelineAccess::createClip(*timeline, zone, clipId, state, audioStream, u, r); }) &&
           step(undo, redo, [&](Fun &u, Fun &r) {
               return timeline->requestClipMove(clipId, trackId, position, true, true, true, true, u, r) == TimelineModel::MoveSuccess;
           });
}

bool cutRange(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const int start = op.frame(QStringLiteral("start_f"));
    const int end = op.frame(QStringLiteral("end_f"));
    const QPoint zone(start, end);
    QVector<int> tracks;
    for (int tid : timeline->getAllTracksIds()) {
        if (!timeline->trackIsLocked(tid)) {
            tracks << tid;
        }
    }
    // Same sequence as TimelineFunctions::extractZoneWithUndo, but on every unlocked track instead of the active (target) ones
    if (!step(undo, redo, [&](Fun &u, Fun &r) { return TimelineFunctions::breakAffectedGroups(timeline, tracks, zone, u, r); })) {
        return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not ungroup the clips crossing the range"));
    }
    for (int tid : std::as_const(tracks)) {
        if (!step(undo, redo, [&](Fun &u, Fun &r) { return TimelineFunctions::liftZone(timeline, tid, zone, u, r); })) {
            return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not cut track %1").arg(timeline->getTrackTagById(tid)));
        }
    }
    if (!step(undo, redo, [&](Fun &u, Fun &r) { return TimelineFunctions::removeSpace(timeline, zone, u, r, tracks, false); })) {
        return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not close the gap"));
    }
    // Guides follow the cut like Extract Zone does when every track is affected
    const auto guides = timeline->getGuideModel();
    if (guides && tracks.size() == int(timeline->getAllTracksIds().size()) && !KdenliveSettings::lockedGuides()) {
        const double fps = pCore->getCurrentFps();
        for (const CommentedTime &guide : guides->getMarkersInRange(start, end - 1)) {
            if (!step(undo, redo, [&](Fun &u, Fun &r) { return guides->removeMarker(guide.time(), u, r); })) {
                return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not remove a guide inside the range"));
            }
        }
        const QList<CommentedTime> later = guides->getMarkersInRange(end, -1);
        if (!later.isEmpty() &&
            !step(undo, redo, [&](Fun &u, Fun &r) { return guides->moveMarkers(later, GenTime(end, fps), GenTime(start, fps), u, r); })) {
            return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not move the guides after the range"));
        }
    }
    return true;
}

bool split(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int at = op.frame(QStringLiteral("at_f"));
    const std::unordered_set<int> before = OpValidator::groupOf(timeline, cid);
    QList<int> cutTracks;
    for (int tid : trackIdsTopDown(timeline)) {
        for (int id : before) {
            const int start = timeline->getClipPosition(id);
            if (timeline->getClipTrackId(id) == tid && start < at && at < start + timeline->getClipPlaytime(id) && !cutTracks.contains(tid)) {
                cutTracks << tid;
            }
        }
    }
    if (!step(undo, redo, [&](Fun &u, Fun &r) { return TimelineFunctions::requestClipCut(timeline, cid, at, u, r); })) {
        return fail(outcome, QStringLiteral("at_f"), QStringLiteral("Kdenlive refused to cut clip %1 at %2").arg(cid).arg(at));
    }
    for (int tid : std::as_const(cutTracks)) {
        const int right = timeline->getClipByPosition(tid, at);
        if (right >= 0 && before.count(right) == 0) {
            outcome.created << right;
        }
    }
    return true;
}

bool trim(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int start = timeline->getClipPosition(cid);
    const int end = start + timeline->getClipPlaytime(cid);
    const int newStart = op.has(QStringLiteral("start_f")) ? op.frame(QStringLiteral("start_f")) : start;
    const int newEnd = op.has(QStringLiteral("end_f")) ? op.frame(QStringLiteral("end_f")) : end;
    const std::unordered_set<int> group = OpValidator::groupOf(timeline, cid);
    // Like TimelineModel::requestItemResize: grouped clips sharing the moved edge follow it. Right edge first, then left.
    for (const bool right : {true, false}) {
        const int edge = right ? end : start;
        const int target = right ? newEnd : newStart;
        if (edge == target) {
            continue;
        }
        for (int id : group) {
            const int position = timeline->getClipPosition(id);
            const int itemEnd = position + timeline->getClipPlaytime(id);
            if ((right ? itemEnd : position) != edge) {
                continue;
            }
            int size = right ? target - position : itemEnd - target;
            if (!step(undo, redo, [&](Fun &u, Fun &r) { return timeline->requestItemResize(id, size, right, true, u, r); })) {
                return fail(outcome, right ? QStringLiteral("end_f") : QStringLiteral("start_f"),
                            QStringLiteral("Kdenlive refused to resize clip %1 to [%2, %3)").arg(id).arg(newStart).arg(newEnd));
            }
        }
    }
    if (timeline->getClipPosition(cid) != newStart || timeline->getClipPosition(cid) + timeline->getClipPlaytime(cid) != newEnd) {
        return fail(outcome, QStringLiteral("end_f"), QStringLiteral("Kdenlive resized clip %1 to a different range").arg(cid));
    }
    return true;
}

bool move(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const int cid = op.frame(QStringLiteral("clip_id"));
    const int at = op.frame(QStringLiteral("at_f"));
    const int currentTrack = timeline->getClipTrackId(cid);
    const int root = OpValidator::groupRoot(timeline, cid);
    bool moved = false;
    if (root >= 0) {
        const int deltaTrack = timeline->getTrackPosition(op.track) - timeline->getTrackPosition(currentTrack);
        const int deltaPos = at - timeline->getClipPosition(cid);
        moved = step(undo, redo, [&](Fun &u, Fun &r) { return timeline->requestGroupMove(cid, root, deltaTrack, deltaPos, true, true, u, r); });
    } else {
        moved = step(undo, redo,
                     [&](Fun &u, Fun &r) { return timeline->requestClipMove(cid, op.track, at, true, true, true, true, u, r) == TimelineModel::MoveSuccess; });
    }
    if (!moved) {
        return fail(outcome, QStringLiteral("at_f"), QStringLiteral("Kdenlive refused to move clip %1 to %2").arg(cid).arg(at));
    }
    if (timeline->getClipPosition(cid) != at || timeline->getClipTrackId(cid) != op.track) {
        return fail(outcome, QStringLiteral("at_f"), QStringLiteral("Kdenlive placed clip %1 somewhere else").arg(cid));
    }
    return true;
}

bool insertClip(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const QString binId = op.string(QStringLiteral("source"));
    const int in = op.frame(QStringLiteral("in_f"));
    const int at = op.frame(QStringLiteral("at_f"));
    const bool audioOnly = timeline->isAudioTrack(op.track);
    int main = -1;
    if (!placeClip(timeline, binId, in, op.outF, audioOnly ? PlaylistState::AudioOnly : PlaylistState::VideoOnly, audioOnly ? op.audioStream : -1, op.track,
                   at, undo, redo, main)) {
        return fail(outcome, QStringLiteral("at_f"), QStringLiteral("Kdenlive could not place \"%1\" on %2").arg(binId, timeline->getTrackTagById(op.track)));
    }
    outcome.created << main;
    if (audioOnly || op.audioTrack < 0) {
        return true;
    }
    int audio = -1;
    if (!placeClip(timeline, binId, in, op.outF, PlaylistState::AudioOnly, op.audioStream, op.audioTrack, at, undo, redo, audio)) {
        return fail(outcome, QStringLiteral("audio_track"),
                    QStringLiteral("Kdenlive could not place the audio of \"%1\" on %2").arg(binId, timeline->getTrackTagById(op.audioTrack)));
    }
    outcome.created << audio;
    if (!step(undo, redo, [&](Fun &u, Fun &r) { return timeline->requestClipsGroup({main, audio}, u, r, GroupType::AVSplit) >= 0; })) {
        return fail(outcome, QStringLiteral("audio_track"), QStringLiteral("Kdenlive could not link the picture and audio clips"));
    }
    return true;
}

bool addMusic(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const QString binId = op.string(QStringLiteral("source"));
    int clip = -1;
    if (!placeClip(timeline, binId, op.frame(QStringLiteral("in_f")), op.outF, PlaylistState::AudioOnly, op.audioStream, op.track,
                   op.frame(QStringLiteral("at_f")), undo, redo, clip)) {
        return fail(outcome, QStringLiteral("at_f"), QStringLiteral("Kdenlive could not place \"%1\" on %2").arg(binId, timeline->getTrackTagById(op.track)));
    }
    outcome.created << clip;
    const double gain = op.number(QStringLiteral("gain_db"));
    if (gain == 0) {
        return true;
    }
    // Kdenlive's "Volume" effect (data/effects/volume.xml, level in dB), added the way pasted effects are. "level" is keyframable,
    // so it must be an MLT animation string: one keyframe at the clip's first frame (a bare number would be read as empty)
    QDomDocument doc;
    QDomElement effects = doc.createElement(QStringLiteral("effects"));
    effects.setAttribute(QStringLiteral("parentIn"), timeline->getClipIn(clip));
    QDomElement effect = doc.createElement(QStringLiteral("effect"));
    effect.setAttribute(QStringLiteral("id"), QStringLiteral("volume"));
    QDomElement level = doc.createElement(QStringLiteral("property"));
    level.setAttribute(QStringLiteral("name"), QStringLiteral("level"));
    level.appendChild(doc.createTextNode(QStringLiteral("0=%1").arg(gain)));
    effect.appendChild(level);
    effects.appendChild(effect);
    doc.appendChild(effects);
    const auto stack = timeline->getClipEffectStackModel(clip);
    if (!stack || !step(undo, redo, [&](Fun &u, Fun &r) { return stack->copyXmlEffectWithUndo(effects, u, r); })) {
        return fail(outcome, QStringLiteral("gain_db"), QStringLiteral("Kdenlive could not add the Volume effect"));
    }
    return true;
}

bool addText(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, TitleStyle style, const QString &text, Fun &undo, Fun &redo,
             OpOutcome &outcome)
{
    const int start = op.frame(QStringLiteral("start_f"));
    const int duration = op.frame(QStringLiteral("end_f")) - start;
    QString name = QString(text).replace(QLatin1Char('\n'), QLatin1Char(' ')).simplified();
    if (name.size() > TitleNameLength) {
        name = name.left(TitleNameLength - 1) + QStringLiteral("…");
    }
    QString binId;
    const QString xml = TitleClip::xml(text, style, pCore->getCurrentFrameSize(), duration);
    if (!step(undo, redo, [&](Fun &u, Fun &r) { return TitleClip::addToBin(xml, duration, name, binId, u, r); })) {
        return fail(outcome, QStringLiteral("text"), QStringLiteral("Kdenlive could not create the title clip"));
    }
    int clip = -1;
    if (!placeClip(timeline, binId, 0, duration, PlaylistState::VideoOnly, -1, op.track, start, undo, redo, clip)) {
        return fail(outcome, QStringLiteral("start_f"), QStringLiteral("Kdenlive could not place the title on %1").arg(timeline->getTrackTagById(op.track)));
    }
    outcome.created << clip;
    return true;
}

bool titleCard(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const TitleStyle style = op.string(QStringLiteral("style")) == QLatin1String("dim") ? TitleStyle::CardDim : TitleStyle::CardBlack;
    return addText(timeline, op, style, op.string(QStringLiteral("text")), undo, redo, outcome);
}

bool caption(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome)
{
    const QString styleName = op.string(QStringLiteral("style"));
    const TitleStyle style = styleName == QLatin1String("top")   ? TitleStyle::CaptionTop
                             : styleName == QLatin1String("pop") ? TitleStyle::CaptionPop
                                                                 : TitleStyle::CaptionBottom;
    const QString speaker = op.string(QStringLiteral("speaker")).trimmed();
    const QString text = op.string(QStringLiteral("text"));
    return addText(timeline, op, style, speaker.isEmpty() ? text : QStringLiteral("%1: %2").arg(speaker, text), undo, redo, outcome);
}

} // namespace

bool step(Fun &undo, Fun &redo, const std::function<bool(Fun &, Fun &)> &request)
{
    // The innermost undo lambda runs last whenever the accumulated undo runs, so it tells whether the request already ran it
    auto rolledBack = std::make_shared<bool>(false);
    Fun localUndo = [rolledBack]() {
        *rolledBack = true;
        return true;
    };
    Fun localRedo = []() { return true; };
    if (!request(localUndo, localRedo)) {
        if (!*rolledBack) {
            localUndo();
        }
        return false;
    }
    UPDATE_UNDO_REDO_NOLOCK(localRedo, localUndo, undo, redo);
    return true;
}

OpFn find(const QString &type)
{
    static const QHash<QString, OpFn> ops{{QStringLiteral("cut_range"), cutRange},   {QStringLiteral("split"), split},
                                          {QStringLiteral("trim"), trim},            {QStringLiteral("move"), move},
                                          {QStringLiteral("insert_clip"), insertClip}, {QStringLiteral("add_music"), addMusic},
                                          {QStringLiteral("title_card"), titleCard}, {QStringLiteral("caption"), caption}};
    return ops.value(type, nullptr);
}

} // namespace ContextCut::TimelineOps
