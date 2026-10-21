/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "jsonrpc.h"

#include <QJsonDocument>
#include <QJsonParseError>
#include <cmath>

namespace ContextCut::JsonRpc {

ParsedFrame parse(const QByteArray &frame)
{
    ParsedFrame parsed;
    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(frame, &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        parsed.error = makeError(ParseError, QStringLiteral("parse_error"), parseError.errorString());
        return parsed;
    }
    if (!doc.isObject()) {
        parsed.error = invalidRequest(doc.isArray() ? QStringLiteral("batch requests are not supported") : QStringLiteral("request must be an object"));
        return parsed;
    }
    const QJsonObject obj = doc.object();
    Request request;
    if (obj.contains(QLatin1String("id"))) {
        request.id = obj.value(QLatin1String("id"));
        if (!request.id.isString() && !request.id.isDouble() && !request.id.isNull()) {
            parsed.error = invalidRequest(QStringLiteral("id must be a number or a string"));
            return parsed;
        }
        parsed.id = request.id;
    }
    if (obj.value(QLatin1String("jsonrpc")).toString() != QLatin1String("2.0")) {
        parsed.error = invalidRequest(QStringLiteral("jsonrpc must be \"2.0\""));
        return parsed;
    }
    request.method = obj.value(QLatin1String("method")).toString();
    if (request.method.isEmpty()) {
        parsed.error = invalidRequest(QStringLiteral("method must be a non-empty string"));
        return parsed;
    }
    const QJsonValue params = obj.value(QLatin1String("params"));
    if (!params.isUndefined() && !params.isNull() && !params.isObject()) {
        parsed.error = invalidParams(QStringLiteral("params"), QStringLiteral("params must be an object"));
        return parsed;
    }
    request.params = params.toObject();
    parsed.request = request;
    return parsed;
}

QByteArray response(const QJsonValue &id, const RpcResult &result)
{
    QJsonObject obj{{QStringLiteral("jsonrpc"), QStringLiteral("2.0")}, {QStringLiteral("id"), id.isUndefined() ? QJsonValue(QJsonValue::Null) : id}};
    if (result.error) {
        QJsonObject data = result.error->data;
        data.insert(QStringLiteral("kind"), result.error->kind);
        obj.insert(QStringLiteral("error"), QJsonObject{{QStringLiteral("code"), result.error->code},
                                                         {QStringLiteral("message"), result.error->message},
                                                         {QStringLiteral("data"), data}});
    } else {
        obj.insert(QStringLiteral("result"), result.result);
    }
    return QJsonDocument(obj).toJson(QJsonDocument::Compact);
}

RpcError makeError(int code, const QString &kind, const QString &message, const QJsonObject &data)
{
    return RpcError{code, kind, message, data};
}

RpcError invalidRequest(const QString &message)
{
    return makeError(InvalidRequest, QStringLiteral("invalid_request"), message);
}

RpcError invalidParams(const QString &field, const QString &message)
{
    return makeError(InvalidParams, QStringLiteral("invalid_params"), message, {{QStringLiteral("field"), field}});
}

RpcError methodNotFound(const QString &method)
{
    return makeError(MethodNotFound, QStringLiteral("method_not_found"), QStringLiteral("unknown method %1").arg(method),
                     {{QStringLiteral("method"), method}});
}

RpcError unauthorized()
{
    return makeError(Unauthorized, QStringLiteral("unauthorized"), QStringLiteral("missing or wrong token; call auth first"));
}

RpcError noProject()
{
    return makeError(NoProject, QStringLiteral("no_project"), QStringLiteral("no project or timeline is open"));
}

RpcError busy()
{
    return makeError(Busy, QStringLiteral("busy"), QStringLiteral("the project is loading or closing; retry shortly"));
}

RpcError staleCursor(qint64 currentRevision)
{
    return makeError(StaleCursor, QStringLiteral("stale_cursor"), QStringLiteral("cursor is invalid or the timeline changed; read again from the start"),
                     {{QStringLiteral("current_revision"), currentRevision}});
}

RpcError notFound(const QJsonValue &id, const QString &message)
{
    return makeError(NotFound, QStringLiteral("not_found"), message, {{QStringLiteral("id"), id}});
}

RpcError internalError(const QString &message)
{
    return makeError(InternalError, QStringLiteral("internal_error"), message);
}

bool optionalInt(const QJsonObject &params, const QString &name, qint64 min, qint64 max, qint64 &out, RpcError &error)
{
    const QJsonValue value = params.value(name);
    if (value.isUndefined() || value.isNull()) {
        return true;
    }
    const double number = value.toDouble(std::nan(""));
    if (!value.isDouble() || std::floor(number) != number || number < double(min) || number > double(max)) {
        error = invalidParams(name, QStringLiteral("%1 must be an integer in %2..%3").arg(name).arg(min).arg(max));
        return false;
    }
    out = qint64(number);
    return true;
}

} // namespace ContextCut::JsonRpc
