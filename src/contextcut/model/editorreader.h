/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "contextcut/bridge/jsonrpc.h"

#include <QJsonArray>
#include <QJsonObject>
#include <memory>

class TimelineItemModel;

namespace ContextCut {
class AiBridgeServer;
}

/** @brief Read-only views of the open project for the AI bridge: get_editor_state, get_timeline, list_recordings
    (docs/protocol.md §8.2–8.4). Everything runs on the GUI thread. */
namespace ContextCut::EditorReader {

/** @brief The timeline shown in the active tab, or nullptr while the GUI or the project is not ready. */
std::shared_ptr<TimelineItemModel> currentTimeline();
/** @brief Like currentTimeline(), but fills @p error with no_project/busy when there is none. */
std::shared_ptr<TimelineItemModel> activeTimeline(JsonRpc::RpcError &error);
/** @brief Tracks in display order (top to bottom). */
QJsonArray tracks(const std::shared_ptr<TimelineItemModel> &timeline);

JsonRpc::RpcResult editorState(qint64 revision, const QString &session);
JsonRpc::RpcResult timelinePage(const QJsonObject &params, qint64 revision);
JsonRpc::RpcResult recordings(const QJsonObject &params, qint64 revision);

/** @brief Registers get_editor_state, get_timeline and list_recordings on @p server. */
void registerReadOnlyMethods(AiBridgeServer &server);

} // namespace ContextCut::EditorReader
