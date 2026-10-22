/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "projectopener.h"
#include "contextcut/bridge/aibridgeserver.h"
#include "core.h"
#include "doc/kdenlivedoc.h"
#include "monitor/monitor.h"
#include "monitor/monitormanager.h"
#include "project/projectmanager.h"

#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QLabel>
#include <QLoggingCategory>
#include <QMessageBox>
#include <QPointer>
#include <QTextDocumentFragment>
#include <QTimer>
#include <QUrl>
#include <QUuid>
#include <algorithm>

Q_LOGGING_CATEGORY(CC_OPEN, "contextcut.open", QtInfoMsg)

namespace ContextCut::ProjectOpener {

namespace {

constexpr int DialogTextMax = 600;

/** Methods the bridge still serves while a project is being opened: none of them touches the project. */
const QStringList AllowedWhileOpening{QStringLiteral("get_open_status"), QStringLiteral("get_confirmation"), QStringLiteral("cancel_confirmation")};

struct OpenRequest
{
    QString id;
    QString path;
    QString state;
    QString message;
};
OpenRequest s_last;
bool s_running = false;

bool samePath(const QString &a, const QString &b)
{
    return !a.isEmpty() && !b.isEmpty() && QDir::cleanPath(a).compare(QDir::cleanPath(b), Qt::CaseInsensitive) == 0;
}

QString plain(const QString &text)
{
    const QString flat = Qt::mightBeRichText(text) ? QTextDocumentFragment::fromHtml(text).toPlainText() : text;
    return flat.simplified().left(DialogTextMax);
}

/** The modal dialog the user is looking at (Kdenlive asking to save, recover, locate missing clips…), so the AI can tell
    them what the app is waiting for. KMessageBox dialogs are plain QDialogs: their message sits in QLabels. */
QJsonValue modalDialog()
{
    const QWidget *dialog = QApplication::activeModalWidget();
    if (dialog == nullptr) {
        return QJsonValue::Null;
    }
    QString text;
    if (const auto *box = qobject_cast<const QMessageBox *>(dialog)) {
        text = box->text();
    } else {
        QStringList parts;
        for (const QLabel *label : dialog->findChildren<QLabel *>()) {
            if (label->isVisible() && !label->text().trimmed().isEmpty()) {
                parts << label->text();
            }
        }
        text = parts.join(QLatin1Char('\n'));
    }
    return QJsonObject{{QStringLiteral("title"), dialog->windowTitle()}, {QStringLiteral("text"), plain(text)}};
}

QJsonObject status()
{
    const bool pending = s_last.state == QLatin1String("pending");
    return {{QStringLiteral("request_id"), s_last.id},
            {QStringLiteral("state"), s_last.state},
            {QStringLiteral("path"), s_last.path},
            {QStringLiteral("dialog"), pending ? modalDialog() : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("message"), s_last.message.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(s_last.message)}};
}

/** Kdenlive arms the project monitor's refreshMonitorTimer (250 ms) when a timeline tab becomes active, i.e. right after a
    project opens. If it fires while the next project loads (doOpenFile spins processEvents with no document),
    Monitor::updateTimelineProducer dereferences the null document and the app crashes. A person cannot open twice that
    fast; an agent can, so wait it out. Milliseconds left, or 0. */
int monitorSettling()
{
    const Monitor *monitor = pCore->monitorManager() ? pCore->monitorManager()->projectMonitor() : nullptr;
    return monitor && monitor->refreshMonitorTimer.isActive() ? std::max(1, monitor->refreshMonitorTimer.remainingTime()) : 0;
}

/** Runs from the main event loop: Kdenlive's dialogs spin their own nested loops in here. */
void run(const QPointer<AiBridgeServer> &bridge, const QString &id, const QString &path)
{
    if (const int wait = monitorSettling()) {
        QTimer::singleShot(wait + 50, pCore->projectManager(), [bridge, id, path]() { run(bridge, id, path); });
        return;
    }
    const QPointer<KdenliveDoc> before = pCore->currentDoc();
    qCInfo(CC_OPEN) << "opening" << path << "request" << id;
    pCore->projectManager()->openFile(QUrl::fromLocalFile(path));
    KdenliveDoc *after = pCore->currentDoc();
    if (s_last.id == id) {
        if (after && samePath(after->url().toLocalFile(), path)) {
            s_last.state = QStringLiteral("opened");
        } else if (before && after == before.data()) {
            s_last.state = QStringLiteral("cancelled");
            s_last.message = QStringLiteral("the current project stayed open: the user cancelled at the save question, saving failed, or a task "
                                            "that cannot be interrupted is running");
        } else {
            s_last.state = QStringLiteral("failed");
            s_last.message = QStringLiteral("Kdenlive could not open the file (the user saw why); an empty project is open instead");
        }
        qCInfo(CC_OPEN) << "open request" << id << s_last.state;
    }
    s_running = false;
    if (bridge) {
        bridge->clearExclusive();
    }
}

JsonRpc::RpcResult open(AiBridgeServer *bridge, const QJsonObject &params)
{
    const QJsonValue value = params.value(QLatin1String("path"));
    const QFileInfo info(value.toString());
    if (!value.isString() || value.toString().isEmpty() || !info.isAbsolute()) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("path"), QStringLiteral("path must be an absolute path to a .kdenlive file")));
    }
    if (info.suffix().compare(QLatin1String("kdenlive"), Qt::CaseInsensitive) != 0) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("path"), QStringLiteral("only .kdenlive project files can be opened")));
    }
    if (!info.exists() || !info.isFile()) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("path"), QStringLiteral("no such file: %1").arg(info.absoluteFilePath())));
    }
    const QString canonical = info.canonicalFilePath();
    if (info.isSymLink() || info.isShortcut() || canonical.isEmpty() || !samePath(info.absoluteFilePath(), canonical)) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::invalidParams(QStringLiteral("path"), QStringLiteral("the path goes through a link; pass the real location (%1)").arg(canonical)));
    }
    if (s_running) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::makeError(JsonRpc::Busy, QStringLiteral("busy"), QStringLiteral("already opening %1 (request %2)").arg(s_last.path, s_last.id)));
    }
    if (!pCore->guiReady() || pCore->projectManager() == nullptr) {
        return JsonRpc::RpcResult::fail(JsonRpc::busy());
    }
    // openFile would run inside that dialog's event loop, under whatever it is in the middle of
    if (const QWidget *dialog = QApplication::activeModalWidget()) {
        return JsonRpc::RpcResult::fail(JsonRpc::makeError(JsonRpc::Busy, QStringLiteral("busy"),
                                                           QStringLiteral("a dialog is open in ContextCut (\"%1\"); wait until the user closes it")
                                                               .arg(dialog->windowTitle())));
    }
    KdenliveDoc *doc = pCore->currentDoc();
    if (doc && doc->isBusy()) {
        return JsonRpc::RpcResult::fail(JsonRpc::busy());
    }
    const bool modified = doc && doc->isModified();
    if (doc && samePath(doc->url().toLocalFile(), canonical)) {
        return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("request_id"), QJsonValue(QJsonValue::Null)},
                                                  {QStringLiteral("state"), QStringLiteral("opened")},
                                                  {QStringLiteral("already_open"), true},
                                                  {QStringLiteral("path"), canonical},
                                                  {QStringLiteral("modified"), modified}});
    }
    const QString id = QStringLiteral("o-") + QUuid::createUuid().toString(QUuid::WithoutBraces);
    s_last = {id, canonical, QStringLiteral("pending"), QString()};
    s_running = true;
    // From here until run() returns, nothing may read or change the project the user may be asked to save
    bridge->setExclusive(QStringLiteral("ContextCut is opening %1 (Kdenlive may be asking the user something, or loading)").arg(info.fileName()),
                         AllowedWhileOpening);
    const QPointer<AiBridgeServer> guard(bridge);
    QTimer::singleShot(0, pCore->projectManager(), [guard, id, canonical]() { run(guard, id, canonical); });
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("request_id"), id},
                                              {QStringLiteral("state"), QStringLiteral("pending")},
                                              {QStringLiteral("path"), canonical},
                                              {QStringLiteral("modified"), modified}});
}

JsonRpc::RpcResult openStatus(const QJsonObject &params)
{
    const QJsonValue id = params.value(QLatin1String("request_id"));
    if (!id.isString() || s_last.id.isEmpty() || id.toString() != s_last.id) {
        return JsonRpc::RpcResult::fail(JsonRpc::notFound(id, QStringLiteral("unknown request_id (only the latest open is remembered)")));
    }
    return JsonRpc::RpcResult::ok(status());
}

} // namespace

void registerMethods(AiBridgeServer &server)
{
    AiBridgeServer *bridge = &server;
    server.registerMethod(QStringLiteral("open_project"), [bridge](const QJsonObject &params) { return open(bridge, params); },
                          AiBridgeServer::MethodKind::Edit);
    server.registerMethod(QStringLiteral("get_open_status"), [](const QJsonObject &params) { return openStatus(params); });
}

} // namespace ContextCut::ProjectOpener
