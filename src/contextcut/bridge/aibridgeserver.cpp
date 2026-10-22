/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "aibridgeserver.h"
#include "contextcut/app/confirmations.h"
#include "contextcut/app/projectopener.h"
#include "contextcut/model/editorreader.h"
#include "contextcut/model/scenereader.h"
#include "contextcut/ops/batchapplier.h"
#include "revisiontracker.h"

#include <QApplication>
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QRandomGenerator>
#include <QSaveFile>
#include <QStandardPaths>
#include <QTimer>
#include <QUuid>
#include <QWidget>
#include <QWebSocket>
#include <QWebSocketCorsAuthenticator>
#include <QWebSocketServer>

Q_LOGGING_CATEGORY(CC_BRIDGE, "contextcut.bridge", QtInfoMsg)

namespace ContextCut {

namespace {

constexpr int Protocol = 1;
constexpr int MaxConnections = 8;
constexpr int AuthTimeoutMs = 5000;
constexpr qint64 MaxMessageBytes = 4 * 1024 * 1024;
// Application close codes (docs/protocol.md §4)
constexpr int CloseUnauthorized = 4401;
constexpr int CloseAuthTimeout = 4408;
constexpr int CloseTooMany = 4429;

QPointer<AiBridgeServer> s_instance;

QString randomToken()
{
    QByteArray bytes(32, Qt::Uninitialized);
    QRandomGenerator::system()->generate(bytes.begin(), bytes.end());
    return QString::fromLatin1(bytes.toHex());
}

/** Compares without exiting early, so timing does not leak how much of the token matched (the length is public). */
bool sameToken(const QString &given, const QString &expected)
{
    const QByteArray x = given.toUtf8();
    const QByteArray y = expected.toUtf8();
    if (x.size() != y.size() || y.isEmpty()) {
        return false;
    }
    unsigned char diff = 0;
    for (qsizetype i = 0; i < x.size(); ++i) {
        diff |= static_cast<unsigned char>(x.at(i) ^ y.at(i));
    }
    return diff == 0;
}

void closeSocket(QWebSocket *socket, int code, const QString &reason)
{
    socket->close(static_cast<QWebSocketProtocol::CloseCode>(code), reason);
}

} // namespace

AiBridgeServer *AiBridgeServer::start(QObject *parent)
{
    if (s_instance) {
        return s_instance;
    }
    auto *server = new AiBridgeServer(parent);
    if (!server->listen()) {
        delete server;
        return nullptr;
    }
    EditorReader::registerReadOnlyMethods(*server);
    SceneReader::registerMethods(*server);
    BatchApplier::registerMethods(*server);
    Confirmations::registerMethods(*server);
    ProjectOpener::registerMethods(*server);
    s_instance = server;
    return server;
}

AiBridgeServer *AiBridgeServer::instance()
{
    return s_instance;
}

AiBridgeServer::AiBridgeServer(QObject *parent)
    : QObject(parent)
    , m_server(new QWebSocketServer(QStringLiteral("ContextCut AI Bridge"), QWebSocketServer::NonSecureMode, this))
    , m_revisions(new RevisionTracker(this))
    , m_token(randomToken())
    , m_session(QUuid::createUuid().toString(QUuid::WithoutBraces))
{
    // Browsers always send Origin; refusing it at the handshake blocks web pages from reaching the bridge
    connect(m_server, &QWebSocketServer::originAuthenticationRequired, this,
            [](QWebSocketCorsAuthenticator *authenticator) { authenticator->setAllowed(authenticator->origin().isEmpty()); });
    connect(m_server, &QWebSocketServer::newConnection, this, &AiBridgeServer::onNewConnection);
    connect(qApp, &QCoreApplication::aboutToQuit, this, &AiBridgeServer::stop);
}

AiBridgeServer::~AiBridgeServer()
{
    stop();
}

void AiBridgeServer::registerMethod(const QString &name, Handler handler, MethodKind kind)
{
    m_methods.insert(name, {std::move(handler), kind});
}

void AiBridgeServer::setExclusive(const QString &reason, const QStringList &allowed)
{
    m_exclusiveReason = reason;
    m_exclusiveAllowed = allowed;
}

void AiBridgeServer::clearExclusive()
{
    m_exclusiveReason.clear();
    m_exclusiveAllowed.clear();
}

quint16 AiBridgeServer::port() const
{
    return m_server->serverPort();
}

QString AiBridgeServer::bridgeFilePath() const
{
    return m_bridgeFile;
}

const QString &AiBridgeServer::session() const
{
    return m_session;
}

RevisionTracker *AiBridgeServer::revisions() const
{
    return m_revisions;
}

bool AiBridgeServer::listen()
{
    if (!m_server->listen(QHostAddress::LocalHost, 0)) {
        qCWarning(CC_BRIDGE) << "AI bridge: cannot listen on 127.0.0.1:" << m_server->errorString();
        return false;
    }
    if (!writeBridgeFile()) {
        m_server->close();
        return false;
    }
    qCInfo(CC_BRIDGE) << "AI bridge listening on 127.0.0.1:" << port() << "info file" << m_bridgeFile;
    return true;
}

bool AiBridgeServer::writeBridgeFile()
{
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (!QDir().mkpath(dir)) {
        qCWarning(CC_BRIDGE) << "AI bridge: cannot create" << dir;
        return false;
    }
    m_bridgeFile = QDir(dir).absoluteFilePath(QStringLiteral("bridge.json"));
    if (QFile::exists(m_bridgeFile)) {
        qCInfo(CC_BRIDGE) << "AI bridge: replacing" << m_bridgeFile << "(stale, or another ContextCut instance)";
    }
    const QDateTime now = QDateTime::currentDateTime();
    const QJsonObject info{{QStringLiteral("protocol"), Protocol},
                           {QStringLiteral("host"), QStringLiteral("127.0.0.1")},
                           {QStringLiteral("port"), int(port())},
                           {QStringLiteral("token"), m_token},
                           {QStringLiteral("session"), m_session},
                           {QStringLiteral("pid"), qint64(QCoreApplication::applicationPid())},
                           {QStringLiteral("app"), QStringLiteral("ContextCut")},
                           {QStringLiteral("app_version"), QCoreApplication::applicationVersion()},
                           {QStringLiteral("started_at"), now.toOffsetFromUtc(now.offsetFromUtc()).toString(Qt::ISODate)}};
    QSaveFile file(m_bridgeFile);
    if (!file.open(QIODevice::WriteOnly) || file.write(QJsonDocument(info).toJson(QJsonDocument::Indented)) < 0 || !file.commit()) {
        qCWarning(CC_BRIDGE) << "AI bridge: cannot write" << m_bridgeFile << file.errorString();
        return false;
    }
    QFile::setPermissions(m_bridgeFile, QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    return true;
}

void AiBridgeServer::removeBridgeFile()
{
    if (m_bridgeFile.isEmpty()) {
        return;
    }
    QFile file(m_bridgeFile);
    if (!file.open(QIODevice::ReadOnly)) {
        return;
    }
    const QString token = QJsonDocument::fromJson(file.readAll()).object().value(QLatin1String("token")).toString();
    file.close();
    // Another instance started later owns the file now; leave it alone
    if (token == m_token) {
        QFile::remove(m_bridgeFile);
        qCInfo(CC_BRIDGE) << "AI bridge: removed" << m_bridgeFile;
    }
}

void AiBridgeServer::stop()
{
    if (m_stopped) {
        return;
    }
    m_stopped = true;
    m_queue.clear();
    const auto sockets = m_connections.keys();
    for (QWebSocket *socket : sockets) {
        socket->abort();
    }
    m_server->close();
    removeBridgeFile();
}

void AiBridgeServer::onNewConnection()
{
    while (QWebSocket *socket = m_server->nextPendingConnection()) {
        socket->setParent(this);
        if (m_stopped || !socket->peerAddress().isLoopback()) {
            socket->abort();
            socket->deleteLater();
            continue;
        }
        if (m_connections.size() >= MaxConnections) {
            closeSocket(socket, CloseTooMany, QStringLiteral("too many connections"));
            socket->deleteLater();
            continue;
        }
        socket->setMaxAllowedIncomingMessageSize(MaxMessageBytes);
        socket->setMaxAllowedIncomingFrameSize(MaxMessageBytes);
        Connection connection;
        connection.authTimer = new QTimer(socket);
        connection.authTimer->setSingleShot(true);
        connect(connection.authTimer, &QTimer::timeout, socket, [socket]() { closeSocket(socket, CloseAuthTimeout, QStringLiteral("auth timeout")); });
        connection.authTimer->start(AuthTimeoutMs);
        m_connections.insert(socket, connection);
        connect(socket, &QWebSocket::textMessageReceived, this, [this, socket](const QString &message) { enqueue(socket, message.toUtf8(), false); });
        connect(socket, &QWebSocket::binaryMessageReceived, this, [this, socket](const QByteArray &message) { enqueue(socket, message, true); });
        connect(socket, &QWebSocket::disconnected, this, [this, socket]() { onSocketGone(socket); });
    }
}

void AiBridgeServer::onSocketGone(QWebSocket *socket)
{
    m_connections.remove(socket);
    socket->deleteLater();
}

void AiBridgeServer::enqueue(QWebSocket *socket, const QByteArray &frame, bool binary)
{
    m_queue.push_back({socket, frame, binary});
    processQueue();
}

void AiBridgeServer::processQueue()
{
    // A handler may spin a nested event loop; frames arriving meanwhile wait in the queue instead of running concurrently
    if (m_processing) {
        return;
    }
    m_processing = true;
    while (!m_queue.empty()) {
        Pending pending = std::move(m_queue.front());
        m_queue.pop_front();
        if (pending.socket && m_connections.contains(pending.socket)) {
            handleFrame(pending.socket, pending.frame, pending.binary);
        }
    }
    m_processing = false;
}

void AiBridgeServer::handleFrame(QWebSocket *socket, const QByteArray &frame, bool binary)
{
    if (binary) {
        send(socket, QJsonValue(QJsonValue::Null), JsonRpc::RpcResult::fail(JsonRpc::invalidRequest(QStringLiteral("binary frames are not supported"))));
        return;
    }
    const JsonRpc::ParsedFrame parsed = JsonRpc::parse(frame);
    if (parsed.error) {
        send(socket, parsed.id, JsonRpc::RpcResult::fail(*parsed.error));
        return;
    }
    const JsonRpc::Request &request = *parsed.request;
    Connection &connection = m_connections[socket];
    if (!connection.authenticated) {
        const QString token = request.params.value(QLatin1String("token")).toString();
        if (request.method != QLatin1String("auth") || !sameToken(token, m_token)) {
            qCInfo(CC_BRIDGE) << "AI bridge: rejected unauthenticated" << request.method;
            send(socket, request.id, JsonRpc::RpcResult::fail(JsonRpc::unauthorized()));
            closeSocket(socket, CloseUnauthorized, QStringLiteral("unauthorized"));
            return;
        }
        connection.authenticated = true;
        connection.authTimer->stop();
        qCInfo(CC_BRIDGE) << "AI bridge: client authenticated" << request.params.value(QLatin1String("client")).toString();
        send(socket, request.id, authResult());
        return;
    }
    if (request.isNotification()) {
        return;
    }
    if (request.method == QLatin1String("auth")) {
        send(socket, request.id, authResult());
        return;
    }
    const auto method = m_methods.constFind(request.method);
    if (method == m_methods.constEnd()) {
        send(socket, request.id, JsonRpc::RpcResult::fail(JsonRpc::methodNotFound(request.method)));
        return;
    }
    if (!m_exclusiveReason.isEmpty() && !m_exclusiveAllowed.contains(request.method)) {
        send(socket, request.id, JsonRpc::RpcResult::fail(JsonRpc::makeError(JsonRpc::Busy, QStringLiteral("busy"), m_exclusiveReason)));
        return;
    }
    // A modal dialog (Kdenlive asking "Save changes?", Project Settings…) runs a nested event loop that also delivers bridge
    // frames; an edit landing then would change the project behind the question the user is answering
    if (method->kind == MethodKind::Edit) {
        if (const QWidget *dialog = QApplication::activeModalWidget()) {
            send(socket, request.id,
                 JsonRpc::RpcResult::fail(JsonRpc::makeError(JsonRpc::Busy, QStringLiteral("busy"),
                                                             QStringLiteral("a dialog is open in ContextCut (\"%1\"); wait until the user closes it")
                                                                 .arg(dialog->windowTitle()))));
            return;
        }
    }
    // The client may disconnect while the handler runs (nested event loop)
    QPointer<QWebSocket> guard(socket);
    const JsonRpc::RpcResult result = method->handler(request.params);
    if (guard) {
        send(guard, request.id, result);
    }
}

JsonRpc::RpcResult AiBridgeServer::authResult()
{
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("protocol"), Protocol},
                                              {QStringLiteral("session"), m_session},
                                              {QStringLiteral("app"), QStringLiteral("ContextCut")},
                                              {QStringLiteral("app_version"), QCoreApplication::applicationVersion()},
                                              {QStringLiteral("revision"), m_revisions->current()}});
}

void AiBridgeServer::send(QWebSocket *socket, const QJsonValue &id, const JsonRpc::RpcResult &result)
{
    socket->sendTextMessage(QString::fromUtf8(JsonRpc::response(id, result)));
}

} // namespace ContextCut
