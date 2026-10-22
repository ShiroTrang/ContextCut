/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "jsonrpc.h"

#include <QHash>
#include <QObject>
#include <QPointer>
#include <QStringList>
#include <deque>
#include <functional>

class QTimer;
class QWebSocket;
class QWebSocketServer;

namespace ContextCut {

class RevisionTracker;

/** @class AiBridgeServer
    @brief Local WebSocket endpoint through which the contextcut-ai MCP service reads and edits the open timeline.

    Listens on 127.0.0.1 only, on a port picked by the OS. The port and a per-launch token are written to bridge.json in
    the user's app data folder; a client must send `auth` with that token first. Requests are JSON-RPC 2.0 and run one
    at a time, in arrival order, on the GUI thread. Contract: docs/protocol.md.
 */
class AiBridgeServer : public QObject
{
    Q_OBJECT
public:
    using Handler = std::function<JsonRpc::RpcResult(const QJsonObject &params)>;
    /** @brief Edit methods change the project; they are refused (busy) while a modal dialog is open in the app. */
    enum class MethodKind { Read, Edit };

    /** @brief Starts the single bridge instance (no-op if already started). Returns nullptr if it could not listen;
        the app keeps running without the bridge in that case. */
    static AiBridgeServer *start(QObject *parent);
    static AiBridgeServer *instance();
    ~AiBridgeServer() override;

    void registerMethod(const QString &name, Handler handler, MethodKind kind = MethodKind::Read);
    /** @brief Until clearExclusive(), every method except @p allowed (and auth) fails with busy and @p reason as message.
        Used while a project is being opened: nothing may touch the project the user is being asked to save. */
    void setExclusive(const QString &reason, const QStringList &allowed);
    void clearExclusive();
    quint16 port() const;
    QString bridgeFilePath() const;
    const QString &session() const;
    RevisionTracker *revisions() const;

private:
    explicit AiBridgeServer(QObject *parent);
    bool listen();
    void stop();
    bool writeBridgeFile();
    void removeBridgeFile();
    void onNewConnection();
    void onSocketGone(QWebSocket *socket);
    void enqueue(QWebSocket *socket, const QByteArray &frame, bool binary);
    void processQueue();
    void handleFrame(QWebSocket *socket, const QByteArray &frame, bool binary);
    JsonRpc::RpcResult authResult();
    void send(QWebSocket *socket, const QJsonValue &id, const JsonRpc::RpcResult &result);

    struct Connection
    {
        bool authenticated{false};
        QTimer *authTimer{nullptr};
    };
    struct Pending
    {
        QPointer<QWebSocket> socket;
        QByteArray frame;
        bool binary{false};
    };

    QWebSocketServer *m_server;
    RevisionTracker *m_revisions;
    QString m_token;
    QString m_session;
    QString m_bridgeFile;
    struct Method
    {
        Handler handler;
        MethodKind kind{MethodKind::Read};
    };
    QHash<QString, Method> m_methods;
    QString m_exclusiveReason;
    QStringList m_exclusiveAllowed;
    QHash<QWebSocket *, Connection> m_connections;
    std::deque<Pending> m_queue;
    bool m_processing{false};
    bool m_stopped{false};
};

} // namespace ContextCut
