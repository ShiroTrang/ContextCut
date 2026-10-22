/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "scenereader.h"
#include "bin/projectclip.h"
#include "contextcut/bridge/aibridgeserver.h"
#include "contextcut/bridge/revisiontracker.h"
#include "core.h"
#include "doc/kdenlivedoc.h"
#include "editorreader.h"
#include "monitor/monitor.h"
#include "monitor/monitormanager.h"
#include "monitor/monitorproxy.h"
#include "project/projectmanager.h"
#include "timeline2/model/timelineitemmodel.hpp"

#include <QBuffer>
#include <QDomDocument>
#include <QImageWriter>
#include <QUrl>
#include <climits>

namespace ContextCut::SceneReader {

namespace {

constexpr qint64 DefaultWidth = 512;
constexpr qint64 DefaultQuality = 80;

QJsonObject profileObject()
{
    const auto [num, den] = pCore->getProjectFpsInfo();
    const QSize size = pCore->getCurrentFrameSize();
    return {{QStringLiteral("fps"), QJsonObject{{QStringLiteral("num"), num}, {QStringLiteral("den"), den}}},
            {QStringLiteral("width"), size.width()},
            {QStringLiteral("height"), size.height()}};
}

} // namespace

JsonRpc::RpcResult scene(const QJsonObject &params, qint64 revision)
{
    JsonRpc::RpcError error;
    const auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    const QJsonValue originalsValue = params.value(QLatin1String("originals"));
    if (!originalsValue.isUndefined() && !originalsValue.isNull() && !originalsValue.isBool()) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("originals"), QStringLiteral("originals must be a boolean")));
    }
    const bool originals = originalsValue.toBool(true);
    KdenliveDoc *doc = pCore->currentDoc();
    // Same call RenderRequest::process makes before writing the render playlist
    const QString folder = doc->url().isEmpty() ? QString() : doc->url().adjusted(QUrl::RemoveFilename | QUrl::StripTrailingSlash).toLocalFile();
    QString xml = pCore->projectManager()->projectSceneList(folder).first;
    if (xml.isEmpty()) {
        return JsonRpc::RpcResult::fail(JsonRpc::internalError(QStringLiteral("Kdenlive returned an empty scene")));
    }
    QDomDocument dom;
    if (!dom.setContent(xml)) {
        return JsonRpc::RpcResult::fail(JsonRpc::internalError(QStringLiteral("Kdenlive returned an unreadable scene")));
    }
    const bool proxies = doc->useProxy();
    if (originals && proxies) {
        KdenliveDoc::useOriginals(dom);
        xml = dom.toString();
    }
    const QString root = dom.documentElement().attribute(QStringLiteral("root"));
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("revision"), revision},
                                              {QStringLiteral("xml"), xml},
                                              {QStringLiteral("root"), root.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(root)},
                                              {QStringLiteral("profile"), profileObject()},
                                              {QStringLiteral("duration_f"), timeline->duration()},
                                              {QStringLiteral("proxies"), proxies}});
}

JsonRpc::RpcResult viewerFrame(const QJsonObject &params)
{
    JsonRpc::RpcError error;
    const auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    const QJsonValue monitorValue = params.value(QLatin1String("monitor"));
    QString which = QStringLiteral("active");
    if (!monitorValue.isUndefined() && !monitorValue.isNull()) {
        which = monitorValue.toString();
        if (!monitorValue.isString() || !QStringList{QStringLiteral("active"), QStringLiteral("project"), QStringLiteral("clip")}.contains(which)) {
            return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("monitor"), QStringLiteral("monitor must be active, project or clip")));
        }
    }
    qint64 at = -1;
    qint64 width = DefaultWidth;
    qint64 quality = DefaultQuality;
    if (!JsonRpc::optionalInt(params, QStringLiteral("at_f"), 0, INT_MAX, at, error) ||
        !JsonRpc::optionalInt(params, QStringLiteral("width"), 64, 1920, width, error) ||
        !JsonRpc::optionalInt(params, QStringLiteral("quality"), 1, 100, quality, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    if (at >= 0 && which == QLatin1String("clip")) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("at_f"), QStringLiteral("at_f moves the project monitor; use monitor project")));
    }
    if (at >= timeline->duration()) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::invalidParams(QStringLiteral("at_f"), QStringLiteral("at_f must be before the end of the sequence (%1)").arg(timeline->duration())));
    }
    if (which == QLatin1String("active")) {
        which = at < 0 && pCore->monitorManager()->isActive(Kdenlive::ClipMonitor) ? QStringLiteral("clip") : QStringLiteral("project");
    }
    Monitor *monitor = pCore->getMonitor(which == QLatin1String("clip") ? Kdenlive::ClipMonitor : Kdenlive::ProjectMonitor);
    if (!monitor) {
        return JsonRpc::RpcResult::fail(JsonRpc::internalError(QStringLiteral("monitor not available")));
    }
    QJsonValue clip(QJsonValue::Null);
    if (which == QLatin1String("clip")) {
        const QString binId = monitor->activeClipId();
        const auto controller = monitor->currentController();
        if (binId.isEmpty() || !controller) {
            return JsonRpc::RpcResult::fail(JsonRpc::notFound(QJsonValue(QJsonValue::Null), QStringLiteral("the clip monitor shows no clip")));
        }
        clip = QJsonObject{{QStringLiteral("source"), binId}, {QStringLiteral("name"), controller->clipName()}};
    }
    if (at >= 0) {
        // Monitor::processSeek seeks the monitor producer synchronously, so the frame below is the one at at_f
        monitor->requestSeek(int(at));
    }
    const QSize display = pCore->getCurrentFrameDisplaySize();
    const int w = int(width) + int(width) % 2;
    const int h = std::max(2, int(qRound(double(w) * display.height() / std::max(1, display.width()) / 2.0)) * 2);
    // Like Kdenlive's Extract Frame: the monitor producer's current frame, with the proxies and effects the user sees
    const QImage image = monitor->getControllerProxy()->extractFrame(QString(), w, h).convertToFormat(QImage::Format_RGB32);
    if (image.isNull()) {
        return JsonRpc::RpcResult::fail(JsonRpc::internalError(QStringLiteral("the monitor returned no frame")));
    }
    QBuffer buffer;
    buffer.open(QIODevice::WriteOnly);
    QImageWriter writer(&buffer, "jpeg");
    writer.setQuality(int(quality));
    if (!writer.write(image)) {
        return JsonRpc::RpcResult::fail(JsonRpc::internalError(QStringLiteral("JPEG encoding failed: %1").arg(writer.errorString())));
    }
    return JsonRpc::RpcResult::ok(QJsonObject{{QStringLiteral("monitor"), which},
                                              {QStringLiteral("position_f"), monitor->position()},
                                              {QStringLiteral("playing"), monitor->isPlaying()},
                                              {QStringLiteral("clip"), clip},
                                              {QStringLiteral("width"), image.width()},
                                              {QStringLiteral("height"), image.height()},
                                              {QStringLiteral("format"), QStringLiteral("jpeg")},
                                              {QStringLiteral("data"), QString::fromLatin1(buffer.data().toBase64())}});
}

void registerMethods(AiBridgeServer &server)
{
    AiBridgeServer *bridge = &server;
    server.registerMethod(QStringLiteral("get_scene"), [bridge](const QJsonObject &params) { return scene(params, bridge->revisions()->current()); });
    server.registerMethod(QStringLiteral("get_viewer_frame"), [](const QJsonObject &params) { return viewerFrame(params); });
}

} // namespace ContextCut::SceneReader
