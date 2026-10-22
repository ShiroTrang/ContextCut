/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "contextcut/bridge/jsonrpc.h"

#include <QJsonArray>
#include <QJsonObject>
#include <memory>

class ProjectClip;
class TimelineItemModel;

namespace ContextCut {
class AiBridgeServer;
}

/** @brief Read-only views of the open project for the AI bridge: get_editor_state, get_timeline, list_recordings, list_sources
    (docs/protocol.md §8.2–8.4b). Everything runs on the GUI thread. */
namespace ContextCut::EditorReader {

/** @brief The timeline shown in the active tab, or nullptr while the GUI or the project is not ready. */
std::shared_ptr<TimelineItemModel> currentTimeline();
/** @brief Like currentTimeline(), but fills @p error with no_project/busy when there is none. */
std::shared_ptr<TimelineItemModel> activeTimeline(JsonRpc::RpcError &error);
/** @brief Undo step text without the "hh:mm " FunctionalUndoCommand puts in front of every label. */
QString undoLabel(const QString &text);
/** @brief Tracks in display order (top to bottom). */
QJsonArray tracks(const std::shared_ptr<TimelineItemModel> &timeline);

JsonRpc::RpcResult editorState(qint64 revision, const QString &session);
JsonRpc::RpcResult timelinePage(const QJsonObject &params, qint64 revision);
JsonRpc::RpcResult recordings(const QJsonObject &params, qint64 revision);
/** @brief One list_sources entry (docs/protocol.md §8.4b). */
QJsonObject sourceObject(const std::shared_ptr<ProjectClip> &clip);
/** @brief Every bin clip (recordings, music, images, titles…), for picking a source id (P1c). */
JsonRpc::RpcResult sources(const QJsonObject &params, qint64 revision);

/** @brief Registers get_editor_state, get_timeline, list_recordings and list_sources on @p server. */
void registerReadOnlyMethods(AiBridgeServer &server);

} // namespace ContextCut::EditorReader
