/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QString>
#include <memory>
#include <unordered_set>

class ProjectClip;
class TimelineItemModel;

namespace ContextCut {

/** @brief An error or warning about one op of a batch (docs/protocol.md §8.5). */
struct OpIssue
{
    int opIndex{-1};
    QString field;
    QString message;

    QJsonObject toJson() const;
};

/** @brief One op of a batch: raw params with defaults filled in, plus what checkState resolved on the current timeline. */
struct Op
{
    int index{-1};
    QString type;
    QJsonObject params;

    // Resolved by OpValidator::checkState
    int track{-1};
    int audioTrack{-1};
    int audioStream{-1};
    int outF{-1};

    bool has(const QString &name) const;
    int frame(const QString &name) const;
    double number(const QString &name) const;
    QString string(const QString &name) const;
    bool flag(const QString &name) const;
};

namespace OpValidator {

/** @brief Static checks of a batch: op types, required params, types and ranges, start < end. Fills defaults. */
QList<Op> parse(const QJsonValue &ops, QList<OpIssue> &errors, QList<OpIssue> &warnings);

/** @brief Checks @p op against the timeline as it is now and resolves its tracks and defaults into @p op.
    Returns false with @p error (field + message) when the op cannot run. */
bool checkState(const std::shared_ptr<TimelineItemModel> &timeline, Op &op, OpIssue &error, QList<OpIssue> &warnings);

/** @brief Track id from an id, a tag ("V1") or a track name; -1 with @p error when not found or ambiguous. */
int resolveTrack(const std::shared_ptr<TimelineItemModel> &timeline, const QJsonValue &ref, OpIssue &error);

/** @brief The clips moved, resized or cut together with @p clipId (its AV/user group, ignoring the temporary selection group). */
std::unordered_set<int> groupOf(const std::shared_ptr<TimelineItemModel> &timeline, int clipId);
/** @brief Top group of @p clipId below the temporary selection group, or -1 when the clip is not grouped. */
int groupRoot(const std::shared_ptr<TimelineItemModel> &timeline, int clipId);

/** @brief Bin clip for a source id, or nullptr. */
std::shared_ptr<ProjectClip> sourceClip(const QString &binId);

} // namespace OpValidator

} // namespace ContextCut
