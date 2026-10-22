/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

namespace ContextCut {
class AiBridgeServer;
}

/** @brief Asks the user in the app before the AI does something it may not do on its own (P2c: export a file).

    request_confirmation shows a non-modal box over the main window and returns at once, so the bridge keeps serving while
    the user decides; the client polls get_confirmation (docs/protocol.md §8.12). The box text is written here from
    structured fields, never taken from the AI. */
namespace ContextCut::Confirmations {

/** @brief Registers request_confirmation, get_confirmation and cancel_confirmation on @p server. */
void registerMethods(AiBridgeServer &server);

} // namespace ContextCut::Confirmations
