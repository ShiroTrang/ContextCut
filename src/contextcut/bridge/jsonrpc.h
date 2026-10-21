/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <optional>

/** @brief JSON-RPC 2.0 framing for the AI bridge. Error codes and kinds follow docs/protocol.md §4. */
namespace ContextCut::JsonRpc {

enum ErrorCode {
    ParseError = -32700,
    InvalidRequest = -32600,
    MethodNotFound = -32601,
    InvalidParams = -32602,
    InternalError = -32603,
    Unauthorized = -32001,
    NoProject = -32002,
    Conflict = -32003,
    StaleCursor = -32004,
    Busy = -32005,
    ValidationFailed = -32006,
    ApplyFailed = -32007,
    NotFound = -32008,
};

struct RpcError
{
    int code{InternalError};
    /** @brief Stable symbolic name, sent as error.data.kind */
    QString kind;
    QString message;
    QJsonObject data;
};

/** @brief What a method handler returns: either a result value or an error. */
struct RpcResult
{
    QJsonValue result;
    std::optional<RpcError> error;

    static RpcResult ok(const QJsonValue &value) { return {value, std::nullopt}; }
    static RpcResult fail(const RpcError &err) { return {QJsonValue(), err}; }
};

struct Request
{
    /** @brief Number or string; undefined for a notification */
    QJsonValue id;
    QString method;
    QJsonObject params;
    bool isNotification() const { return id.isUndefined(); }
};

/** @brief Result of parsing one text frame: a request, or an error to send back with @p id (null when unreadable). */
struct ParsedFrame
{
    std::optional<Request> request;
    std::optional<RpcError> error;
    QJsonValue id{QJsonValue::Null};
};

ParsedFrame parse(const QByteArray &frame);
QByteArray response(const QJsonValue &id, const RpcResult &result);

RpcError makeError(int code, const QString &kind, const QString &message, const QJsonObject &data = {});
RpcError invalidRequest(const QString &message);
RpcError invalidParams(const QString &field, const QString &message);
RpcError methodNotFound(const QString &method);
RpcError unauthorized();
RpcError noProject();
RpcError busy();
RpcError staleCursor(qint64 currentRevision);
RpcError notFound(const QJsonValue &id, const QString &message);
RpcError internalError(const QString &message);

/** @brief Reads an optional integer param into @p out (unchanged when absent or null).
 *  Returns false and fills @p error when it is present but not an integer in [min, max]. */
bool optionalInt(const QJsonObject &params, const QString &name, qint64 min, qint64 max, qint64 &out, RpcError &error);

} // namespace ContextCut::JsonRpc
