/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

namespace ContextCut {
class AiBridgeServer;
}

/** @brief The AI bridge's editing methods (docs/protocol.md §8.5–8.8): list_operations, validate_operations, apply_operations,
    add_markers, undo_batch, import_media. Each applied batch is exactly one labelled undo step; a failing op undoes the whole batch. */
namespace ContextCut::BatchApplier {

void registerMethods(AiBridgeServer &server);

} // namespace ContextCut::BatchApplier
