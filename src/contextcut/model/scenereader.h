/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "contextcut/bridge/jsonrpc.h"

#include <QJsonObject>

namespace ContextCut {
class AiBridgeServer;
}

/** @brief What the AI sees of the edited picture (P2b, docs/protocol.md §8.10–8.11): the open sequence as the MLT XML Kdenlive
    renders from (melt draws frames from it in the contextcut-ai worker), and the frame a monitor shows right now. GUI thread. */
namespace ContextCut::SceneReader {

/** @brief get_scene: projectSceneList of the active sequence, proxies replaced by the original files unless originals is false. */
JsonRpc::RpcResult scene(const QJsonObject &params, qint64 revision);
/** @brief get_viewer_frame: the active/project/clip monitor frame as base64 JPEG, after an optional seek of the project monitor. */
JsonRpc::RpcResult viewerFrame(const QJsonObject &params);

/** @brief Registers get_scene and get_viewer_frame on @p server. */
void registerMethods(AiBridgeServer &server);

} // namespace ContextCut::SceneReader
