/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "opvalidator.h"
#include "undohelper.hpp"

#include <QList>
#include <QString>
#include <functional>
#include <memory>

class TimelineItemModel;

namespace ContextCut {

/** @brief What one op did: new clip ids, warnings, or why it failed. */
struct OpOutcome
{
    QList<int> created;
    QList<OpIssue> warnings;
    QString field;
    QString error;
};

/** @brief Runs one op (already checked by OpValidator::checkState) and accumulates its undo/redo into the batch's.
    Returns false with outcome.error on failure; every change it made is then in @p undo, so the caller undoes the whole batch once. */
using OpFn = bool (*)(const std::shared_ptr<TimelineItemModel> &timeline, const Op &op, Fun &undo, Fun &redo, OpOutcome &outcome);

namespace TimelineOps {

OpFn find(const QString &type);

/** @brief Runs one Kdenlive request with its own undo/redo accumulators and appends them to @p undo / @p redo on success.
    On failure the request's own changes are reverted exactly once: some Kdenlive functions run the accumulated undo themselves
    before returning false (TimelineFunctions::requestClipCut, removeSpace), others leave it to the caller. */
bool step(Fun &undo, Fun &redo, const std::function<bool(Fun &, Fun &)> &request);

} // namespace TimelineOps

} // namespace ContextCut
