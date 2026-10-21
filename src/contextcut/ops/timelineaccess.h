/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "bin/model/markerlistmodel.hpp"
#include "timeline2/model/clipmodel.hpp"
#include "timeline2/model/groupsmodel.hpp"
#include "timeline2/model/timelineitemmodel.hpp"
#include "timeline2/model/trackmodel.hpp"

namespace ContextCut {

/** @brief Reaches the few protected TimelineModel members the AI ops need, without patching Kdenlive.

    Never instantiated: a class derived from TimelineModel may form pointers to its protected members
    (&TimelineAccess::member has type "member of TimelineModel"), which can then be applied to any timeline.
    Kdenlive's own helpers (TimelineFunctions, TimelineController) are friends of TimelineModel instead.
 */
struct TimelineAccess : TimelineModel
{
    TimelineAccess() = delete;

    /** @brief TimelineModel::requestClipCreation: a clip of @p binClipId ("id/in/out", out inclusive) not yet on a track. */
    static bool createClip(TimelineModel &timeline, const QString &binClipId, int &id, PlaylistState::ClipState state, int audioStream, Fun &undo,
                           Fun &redo)
    {
        return (timeline.*&TimelineAccess::requestClipCreation)(binClipId, id, state, audioStream, 1.0, false, undo, redo);
    }
    static std::shared_ptr<TrackModel> track(const TimelineModel &timeline, int trackId)
    {
        return (timeline.*&TimelineAccess::getTrackById_const)(trackId);
    }
    static std::shared_ptr<ClipModel> clip(const TimelineModel &timeline, int clipId) { return (timeline.*&TimelineAccess::getClipPtr)(clipId); }
    static GroupsModel &groups(const TimelineModel &timeline) { return *(timeline.*&TimelineAccess::m_groups); }
};

/** @brief Same trick for ClipModel::getMaxDuration (source length in the clip's frames, -1 when unlimited). */
struct ClipAccess : ClipModel
{
    ClipAccess() = delete;
    static int maxDuration(const ClipModel &clip) { return (clip.*&ClipAccess::getMaxDuration)(); }
};

/** @brief Same trick for the undo-accumulating MarkerListModel::addMarker (the public one pushes its own undo step). */
struct MarkerAccess : MarkerListModel
{
    MarkerAccess() = delete;
    static bool add(MarkerListModel &markers, GenTime pos, const QString &comment, int type, Fun &undo, Fun &redo)
    {
        using AddMarker = bool (MarkerListModel::*)(GenTime, const QString &, int, Fun &, Fun &);
        return (markers.*static_cast<AddMarker>(&MarkerAccess::addMarker))(pos, comment, type, undo, redo);
    }
};

} // namespace ContextCut
