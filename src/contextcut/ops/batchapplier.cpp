/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "batchapplier.h"
#include "bin/model/markerlistmodel.hpp"
#include "contextcut/bridge/aibridgeserver.h"
#include "contextcut/bridge/revisiontracker.h"
#include "contextcut/model/editorreader.h"
#include "core.h"
#include "doc/docundostack.hpp"
#include "opregistry.h"
#include "opvalidator.h"
#include "timeline2/model/timelineitemmodel.hpp"
#include "timelineaccess.h"
#include "timelineops.h"

#include <QCoreApplication>
#include <QHash>
#include <QLoggingCategory>
#include <QRegularExpression>
#include <QSet>
#include <QUuid>
#include <climits>

Q_LOGGING_CATEGORY(CC_OPS, "contextcut.ops", QtInfoMsg)

namespace ContextCut::BatchApplier {

namespace {

constexpr int LabelMax = 200;
constexpr int ReasonMax = 500;
constexpr int MarkersMax = 500;
constexpr int CommentMax = 500;
constexpr int StatusTimeoutMs = 5000;

/** Undo commands pushed by the bridge, so undo_batch can tell whether one is still the top of the stack. */
struct Batch
{
    const QUndoCommand *command;
    QString label;
};
QHash<QString, Batch> s_batches;

JsonRpc::RpcError conflict(qint64 currentRevision, const QString &message)
{
    return JsonRpc::makeError(JsonRpc::Conflict, QStringLiteral("conflict"), message, {{QStringLiteral("current_revision"), currentRevision}});
}

JsonRpc::RpcError validationFailed(const QList<OpIssue> &errors)
{
    QJsonArray list;
    for (const OpIssue &error : errors) {
        list.append(error.toJson());
    }
    const QString first = errors.isEmpty() ? QString() : errors.first().message;
    return JsonRpc::makeError(JsonRpc::ValidationFailed, QStringLiteral("validation_failed"),
                              QStringLiteral("%1 invalid op parameter(s), nothing changed: %2").arg(errors.size()).arg(first), {{QStringLiteral("errors"), list}});
}

JsonRpc::RpcError applyFailed(int opIndex, const QString &field, const QString &reason)
{
    QJsonObject data{{QStringLiteral("op_index"), opIndex}, {QStringLiteral("reason"), reason}};
    if (!field.isEmpty()) {
        data.insert(QStringLiteral("field"), field);
    }
    return JsonRpc::makeError(JsonRpc::ApplyFailed, QStringLiteral("apply_failed"),
                              QStringLiteral("op %1 failed, the whole batch was undone: %2").arg(opIndex).arg(reason), data);
}

QJsonArray toJson(const QList<OpIssue> &issues)
{
    QJsonArray list;
    for (const OpIssue &issue : issues) {
        list.append(issue.toJson());
    }
    return list;
}

/** "cắt đoạn chết" and "ai:cắt đoạn chết" both become "AI: cắt đoạn chết". */
QString normalisedLabel(const QString &label)
{
    QString text = label.trimmed();
    text.remove(QRegularExpression(QStringLiteral("^AI:\\s*"), QRegularExpression::CaseInsensitiveOption));
    return QStringLiteral("AI: ") + text;
}

/** Reads the required base_revision and the label (or @p defaultLabel). */
bool readBatchHeader(const QJsonObject &params, const QString &defaultLabel, qint64 &baseRevision, QString &label, JsonRpc::RpcError &error)
{
    baseRevision = -1;
    if (!JsonRpc::optionalInt(params, QStringLiteral("base_revision"), 0, LLONG_MAX / 2, baseRevision, error)) {
        return false;
    }
    if (baseRevision < 0) {
        error = JsonRpc::invalidParams(QStringLiteral("base_revision"), QStringLiteral("base_revision is required: the revision you last read"));
        return false;
    }
    const QJsonValue value = params.value(QLatin1String("label"));
    if ((value.isUndefined() || value.isNull()) && !defaultLabel.isEmpty()) {
        label = defaultLabel;
        return true;
    }
    const QString text = value.toString().trimmed();
    if (!value.isString() || text.isEmpty() || text.size() > LabelMax) {
        error = JsonRpc::invalidParams(QStringLiteral("label"), QStringLiteral("label must be a string of 1..%1 characters, e.g. \"AI: cắt đoạn chết\"").arg(LabelMax));
        return false;
    }
    label = normalisedLabel(text);
    return true;
}

void showStatus(const QString &message, MessageType type, int timeout = -1)
{
    if (pCore->window()) {
        pCore->displayMessage(message, type, timeout);
    }
}

QString shortLabel(const QString &label)
{
    return label.mid(4); // without "AI: "
}

/** Pushes the batch as one undo step and remembers it for undo_batch. */
QString pushBatch(const Fun &undo, const Fun &redo, const QString &label)
{
    auto *command = new FunctionalUndoCommand(undo, redo, label);
    pCore->pushUndo(command);
    const QString id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    s_batches.insert(id, {command, label});
    return id;
}

JsonRpc::RpcResult validateOperations(const QJsonObject &params)
{
    JsonRpc::RpcError error;
    const auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    QList<OpIssue> errors;
    QList<OpIssue> warnings;
    QList<Op> ops = OpValidator::parse(params.value(QLatin1String("ops")), errors, warnings);
    QSet<int> invalid;
    for (const OpIssue &issue : std::as_const(errors)) {
        invalid.insert(issue.opIndex);
    }
    for (Op &op : ops) {
        if (invalid.contains(op.index)) {
            continue;
        }
        OpIssue stateError;
        if (OpValidator::checkState(timeline, op, stateError, warnings)) {
            continue;
        }
        if (op.index == 0) {
            errors << stateError;
        } else {
            // Earlier ops of the batch change the timeline this op will meet; apply checks it again at its turn
            stateError.message += QStringLiteral(" (checked against the current timeline; earlier ops of this batch may change it, apply re-checks)");
            warnings << stateError;
        }
    }
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("ok"), errors.isEmpty()},
                                              {QStringLiteral("errors"), toJson(errors)},
                                              {QStringLiteral("warnings"), toJson(warnings)}});
}

JsonRpc::RpcResult applyOperations(AiBridgeServer *bridge, const QJsonObject &params)
{
    JsonRpc::RpcError error;
    auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 baseRevision = -1;
    QString label;
    if (!readBatchHeader(params, QString(), baseRevision, label, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const QJsonValue reason = params.value(QLatin1String("reason"));
    if (!reason.isUndefined() && !reason.isNull() && (!reason.isString() || reason.toString().size() > ReasonMax)) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("reason"), QStringLiteral("reason must be a string of at most %1 characters").arg(ReasonMax)));
    }

    // Paint the status before checking the revision; user input stays queued so it cannot slip in between
    showStatus(QStringLiteral("AI đang sửa: %1…").arg(shortLabel(label)), ProcessingJobMessage);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    const qint64 current = bridge->revisions()->current();
    if (baseRevision != current) {
        showStatus(QStringLiteral("AI: đợt \"%1\" bị từ chối vì timeline vừa đổi; AI sẽ đọc lại.").arg(shortLabel(label)), InformationMessage, StatusTimeoutMs);
        return JsonRpc::RpcResult::fail(conflict(current, QStringLiteral("base_revision %1 is stale (current %2): read the timeline again").arg(baseRevision).arg(current)));
    }
    QList<OpIssue> errors;
    QList<OpIssue> warnings;
    QList<Op> ops = OpValidator::parse(params.value(QLatin1String("ops")), errors, warnings);
    if (!errors.isEmpty()) {
        showStatus(QStringLiteral("AI: đợt \"%1\" sai tham số, không đổi gì.").arg(shortLabel(label)), InformationMessage, StatusTimeoutMs);
        return JsonRpc::RpcResult::fail(validationFailed(errors));
    }

    // A selection group would make grouped clips move or cut together with whatever the user selected
    timeline->requestClearSelection();
    Fun undo = []() { return true; };
    Fun redo = []() { return true; };
    QJsonObject created;
    for (Op &op : ops) {
        OpIssue stateError;
        OpOutcome outcome;
        const bool ok = OpValidator::checkState(timeline, op, stateError, warnings) && TimelineOps::find(op.type)(timeline, op, undo, redo, outcome);
        if (!ok) {
            undo();
            const QString field = stateError.message.isEmpty() ? outcome.field : stateError.field;
            const QString message = stateError.message.isEmpty() ? outcome.error : stateError.message;
            qCInfo(CC_OPS) << "AI batch" << label << "failed at op" << op.index << op.type << message;
            showStatus(QStringLiteral("AI: đợt \"%1\" lỗi ở op %2, đã hoàn tác cả đợt.").arg(shortLabel(label)).arg(op.index), InformationMessage, StatusTimeoutMs);
            return JsonRpc::RpcResult::fail(applyFailed(op.index, field, message));
        }
        warnings << outcome.warnings;
        if (!outcome.created.isEmpty()) {
            QJsonArray ids;
            for (int id : std::as_const(outcome.created)) {
                ids.append(id);
            }
            created.insert(QString::number(op.index), ids);
        }
    }
    const QString batchId = pushBatch(undo, redo, label);
    qCInfo(CC_OPS) << "AI batch" << batchId << label << ops.size() << "ops; reason:" << reason.toString();
    showStatus(QStringLiteral("%1 — xong. Ctrl+Z để hoàn tác.").arg(label), OperationCompletedMessage, StatusTimeoutMs);
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("batch_id"), batchId},
                                              {QStringLiteral("revision"), bridge->revisions()->current()},
                                              {QStringLiteral("label"), label},
                                              {QStringLiteral("created"), created},
                                              {QStringLiteral("warnings"), toJson(warnings)}});
}

JsonRpc::RpcResult addMarkers(AiBridgeServer *bridge, const QJsonObject &params)
{
    JsonRpc::RpcError error;
    const auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    qint64 baseRevision = -1;
    QString label;
    if (!readBatchHeader(params, QStringLiteral("AI: thêm marker"), baseRevision, label, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const qint64 current = bridge->revisions()->current();
    if (baseRevision != current) {
        return JsonRpc::RpcResult::fail(conflict(current, QStringLiteral("base_revision %1 is stale (current %2): read the timeline again").arg(baseRevision).arg(current)));
    }
    const QJsonValue markers = params.value(QLatin1String("markers"));
    if (!markers.isArray() || markers.toArray().isEmpty() || markers.toArray().size() > MarkersMax) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("markers"), QStringLiteral("markers must be an array of 1..%1 {f, comment, category?}").arg(MarkersMax)));
    }
    const auto guides = timeline->getGuideModel();
    if (!guides) {
        return JsonRpc::RpcResult::fail(JsonRpc::noProject());
    }
    QList<OpIssue> errors;
    const QJsonArray list = markers.toArray();
    for (int i = 0; i < list.size(); ++i) {
        const QJsonObject marker = list.at(i).toObject();
        const QJsonValue frame = marker.value(QLatin1String("f"));
        const QJsonValue comment = marker.value(QLatin1String("comment"));
        const QJsonValue category = marker.value(QLatin1String("category"));
        if (!frame.isDouble() || frame.toDouble() < 0 || frame.toDouble() > INT_MAX || frame.toDouble() != double(frame.toInt())) {
            errors << OpIssue{i, QStringLiteral("f"), QStringLiteral("f must be a frame number >= 0")};
        }
        if (!comment.isString() || comment.toString().size() > CommentMax) {
            errors << OpIssue{i, QStringLiteral("comment"), QStringLiteral("comment must be a string of at most %1 characters").arg(CommentMax)};
        }
        if (!category.isUndefined() && !category.isNull() && !(category.isDouble() && pCore->markerTypes.contains(category.toInt()))) {
            QStringList known;
            for (auto it = pCore->markerTypes.cbegin(); it != pCore->markerTypes.cend(); ++it) {
                known << QStringLiteral("%1 %2").arg(it.key()).arg(it.value().displayName);
            }
            errors << OpIssue{i, QStringLiteral("category"), QStringLiteral("unknown guide category; this project has: %1").arg(known.join(QLatin1String(", ")))};
        }
    }
    if (!errors.isEmpty()) {
        return JsonRpc::RpcResult::fail(validationFailed(errors));
    }
    Fun undo = []() { return true; };
    Fun redo = []() { return true; };
    const double fps = pCore->getCurrentFps();
    for (int i = 0; i < list.size(); ++i) {
        const QJsonObject marker = list.at(i).toObject();
        const QJsonValue category = marker.value(QLatin1String("category"));
        const int type = category.isDouble() ? category.toInt() : -1;
        if (!TimelineOps::step(undo, redo, [&](Fun &u, Fun &r) {
                return MarkerAccess::add(*guides, GenTime(marker.value(QLatin1String("f")).toInt(), fps), marker.value(QLatin1String("comment")).toString(),
                                         type, u, r);
            })) {
            undo();
            return JsonRpc::RpcResult::fail(applyFailed(i, QStringLiteral("f"), QStringLiteral("Kdenlive could not add the guide")));
        }
    }
    const QString batchId = pushBatch(undo, redo, label);
    showStatus(QStringLiteral("%1 — xong. Ctrl+Z để hoàn tác.").arg(label), OperationCompletedMessage, StatusTimeoutMs);
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("batch_id"), batchId},
                                              {QStringLiteral("revision"), bridge->revisions()->current()},
                                              {QStringLiteral("added"), list.size()}});
}

JsonRpc::RpcResult undoBatch(AiBridgeServer *bridge, const QJsonObject &params)
{
    JsonRpc::RpcError error;
    if (!EditorReader::activeTimeline(error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const QJsonValue id = params.value(QLatin1String("batch_id"));
    const auto batch = s_batches.constFind(id.toString());
    if (!id.isString() || batch == s_batches.constEnd()) {
        return JsonRpc::RpcResult::fail(JsonRpc::notFound(id, QStringLiteral("unknown batch_id (batches are forgotten when the app restarts)")));
    }
    const auto stack = pCore->undoStack();
    const int index = stack->index();
    if (index < 1 || stack->command(index - 1) != batch->command) {
        const QString top = EditorReader::undoLabel(stack->undoText());
        return JsonRpc::RpcResult::fail(conflict(bridge->revisions()->current(),
                                                 QStringLiteral("batch \"%1\" is not the latest undo step (next undo: \"%2\"); undo by hand in the app")
                                                     .arg(batch->label, top.isEmpty() ? QStringLiteral("none") : top)));
    }
    stack->undo();
    showStatus(QStringLiteral("Đã hoàn tác: %1").arg(batch->label), OperationCompletedMessage, StatusTimeoutMs);
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("revision"), bridge->revisions()->current()}, {QStringLiteral("undone"), batch->label}});
}

} // namespace

void registerMethods(AiBridgeServer &server)
{
    AiBridgeServer *bridge = &server;
    server.registerMethod(QStringLiteral("list_operations"), [](const QJsonObject &) { return JsonRpc::RpcResult::ok(OpRegistry::listOperations()); });
    server.registerMethod(QStringLiteral("validate_operations"), [](const QJsonObject &params) { return validateOperations(params); });
    server.registerMethod(QStringLiteral("apply_operations"), [bridge](const QJsonObject &params) { return applyOperations(bridge, params); });
    server.registerMethod(QStringLiteral("add_markers"), [bridge](const QJsonObject &params) { return addMarkers(bridge, params); });
    server.registerMethod(QStringLiteral("undo_batch"), [bridge](const QJsonObject &params) { return undoBatch(bridge, params); });
}

} // namespace ContextCut::BatchApplier
