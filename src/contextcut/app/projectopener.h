/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

namespace ContextCut {
class AiBridgeServer;
}

/** @brief open_project and get_open_status (docs/protocol.md §8.13).

    The open runs from the main event loop, exactly like File › Open, so Kdenlive's own dialogs (save changes, file
    recovery, missing clips) ask the user and nothing is decided for them. The bridge only answers get_open_status (and
    confirmations) until the open is over. */
namespace ContextCut::ProjectOpener {

void registerMethods(AiBridgeServer &server);

} // namespace ContextCut::ProjectOpener
