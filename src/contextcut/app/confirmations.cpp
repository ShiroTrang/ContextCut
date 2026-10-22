/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "confirmations.h"
#include "bin/projectclip.h"
#include "bin/projectitemmodel.h"
#include "contextcut/bridge/aibridgeserver.h"
#include "contextcut/bridge/revisiontracker.h"
#include "contextcut/model/editorreader.h"
#include "core.h"
#include "doc/kdenlivedoc.h"
#include "mainwindow.h"
#include "timeline2/model/timelineitemmodel.hpp"

#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QHash>
#include <QLoggingCategory>
#include <QMessageBox>
#include <QPointer>
#include <QPushButton>
#include <QTimer>
#include <QUuid>
#include <algorithm>
#include <climits>

Q_LOGGING_CATEGORY(CC_CONFIRM, "contextcut.confirm", QtInfoMsg)

namespace ContextCut::Confirmations {

namespace {

constexpr int MaxPending = 4;
constexpr int MaxRemembered = 64;
constexpr int ExpireMs = 15 * 60 * 1000;
// Keys pressed while the box pops up must not accept it: the accept button wakes up after this delay
constexpr int ArmDelayMs = 1500;

const QHash<QString, QString> Presets{{QStringLiteral("youtube-1080p60"), QStringLiteral("YouTube 1080p60 (H.264)")},
                                      {QStringLiteral("project"), QStringLiteral("H.264 theo kích thước và fps của project")}};
const QHash<QString, QString> Encoders{{QStringLiteral("auto"), QStringLiteral("NVENC (GPU), lỗi thì x264")},
                                       {QStringLiteral("nvenc"), QStringLiteral("NVENC (GPU)")},
                                       {QStringLiteral("x264"), QStringLiteral("x264 (CPU)")}};

struct Entry
{
    QString state{QStringLiteral("pending")};
    QJsonValue revision{QJsonValue::Null};
    QPointer<QMessageBox> box;
    /** The project asked about: an answer given after another project was opened must not export that one */
    QPointer<KdenliveDoc> doc;
};
QHash<QString, Entry> s_entries;
QStringList s_order;

QJsonObject view(const QString &id, const Entry &entry)
{
    return {{QStringLiteral("confirm_id"), id}, {QStringLiteral("state"), entry.state}, {QStringLiteral("revision"), entry.revision}};
}

/** Frame count as mm:ss.ff (h:mm:ss.ff from one hour), ff = frame within the second: the timecodes the AI tools print
    (contextcut_ai.transcript.timecode). */
QString timecode(qint64 frames, double fps)
{
    const qint64 perSecond = std::max<qint64>(1, qRound64(fps));
    const qint64 seconds = frames / perSecond;
    const QString tail = QStringLiteral("%1.%2").arg(seconds % 60, 2, 10, QLatin1Char('0')).arg(frames % perSecond, 2, 10, QLatin1Char('0'));
    if (seconds >= 3600) {
        return QStringLiteral("%1:%2:%3").arg(seconds / 3600).arg(seconds / 60 % 60, 2, 10, QLatin1Char('0')).arg(tail);
    }
    return QStringLiteral("%1:%2").arg(seconds / 60, 2, 10, QLatin1Char('0')).arg(tail);
}

QString cleanPath(const QString &path)
{
    return QDir::cleanPath(QFileInfo(path).absoluteFilePath());
}

/** Files the export must never replace: every bin clip's file and proxy, and the project file. */
QString protectedMatch(const QString &output)
{
    const QString target = cleanPath(output);
    const auto same = [&target](const QString &path) { return !path.isEmpty() && cleanPath(path).compare(target, Qt::CaseInsensitive) == 0; };
    if (KdenliveDoc *doc = pCore->currentDoc(); doc && same(doc->url().toLocalFile())) {
        return QStringLiteral("the project file");
    }
    const auto model = pCore->projectItemModel();
    for (const QString &binId : model->getAllClipIds()) {
        const auto clip = model->getClipByBinID(binId);
        if (!clip) {
            continue;
        }
        if (same(clip->url())) {
            return QStringLiteral("the file of bin clip %1").arg(binId);
        }
        // A clip still loading holds its producer lock on the GUI thread (EditorReader::stillLoading): skip its proxy
        if (clip->clipStatus() != FileStatus::StatusWaiting) {
            const QString proxy = clip->getProducerProperty(QStringLiteral("kdenlive:proxy"));
            if (proxy.size() > 1 && same(proxy)) {
                return QStringLiteral("the proxy of bin clip %1").arg(binId);
            }
        }
    }
    return {};
}

void remember(const QString &id, const Entry &entry)
{
    s_entries.insert(id, entry);
    s_order.append(id);
    // Forget the oldest answered requests; pending ones stay until answered
    for (int i = 0; s_order.size() > MaxRemembered && i < s_order.size();) {
        if (s_entries.value(s_order.at(i)).state == QLatin1String("pending")) {
            ++i;
            continue;
        }
        s_entries.remove(s_order.takeAt(i));
    }
}

/** Records the answer. @p bridge null: the project is being destroyed, so no revision is read (RevisionTracker::sync would
    touch the half-destroyed document). */
void answer(AiBridgeServer *bridge, const QString &id, const QString &state)
{
    auto it = s_entries.find(id);
    if (it == s_entries.end() || it->state != QLatin1String("pending")) {
        return;
    }
    it->state = state;
    it->revision = bridge ? QJsonValue(bridge->revisions()->current()) : QJsonValue(QJsonValue::Null);
    qCInfo(CC_CONFIRM) << "confirmation" << id << state;
}

JsonRpc::RpcResult request(AiBridgeServer *bridge, const QJsonObject &params)
{
    JsonRpc::RpcError error;
    const auto timeline = EditorReader::activeTimeline(error);
    if (!timeline) {
        return JsonRpc::RpcResult::fail(error);
    }
    if (params.value(QLatin1String("kind")).toString() != QLatin1String("export")) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("kind"), QStringLiteral("kind must be \"export\"")));
    }
    const QString output = params.value(QLatin1String("output")).toString();
    const QFileInfo info(output);
    if (output.isEmpty() || !info.isAbsolute() || info.suffix().compare(QLatin1String("mp4"), Qt::CaseInsensitive) != 0) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("output"), QStringLiteral("output must be an absolute path ending in .mp4")));
    }
    if (const QString match = protectedMatch(output); !match.isEmpty()) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::invalidParams(QStringLiteral("output"), QStringLiteral("output is %1; exporting must never overwrite source media").arg(match)));
    }
    qint64 start = -1;
    qint64 end = -1;
    if (!JsonRpc::optionalInt(params, QStringLiteral("start_f"), 0, INT_MAX, start, error) ||
        !JsonRpc::optionalInt(params, QStringLiteral("end_f"), 1, INT_MAX, end, error)) {
        return JsonRpc::RpcResult::fail(error);
    }
    const int duration = timeline->duration();
    if (start < 0 || end <= start || end > duration) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::invalidParams(QStringLiteral("end_f"), QStringLiteral("need 0 <= start_f < end_f <= %1 (sequence length)").arg(duration)));
    }
    const QString preset = params.value(QLatin1String("preset")).toString();
    const QString encoder = params.value(QLatin1String("encoder")).toString();
    if (!Presets.contains(preset)) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("preset"), QStringLiteral("unknown preset")));
    }
    if (!Encoders.contains(encoder)) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("encoder"), QStringLiteral("encoder must be auto, nvenc or x264")));
    }
    const QJsonValue overwriteValue = params.value(QLatin1String("overwrite"));
    if (!overwriteValue.isUndefined() && !overwriteValue.isNull() && !overwriteValue.isBool()) {
        return JsonRpc::RpcResult::fail(JsonRpc::invalidParams(QStringLiteral("overwrite"), QStringLiteral("overwrite must be a boolean")));
    }
    const bool overwrite = overwriteValue.toBool(false);
    const int pending = int(std::count_if(s_entries.cbegin(), s_entries.cend(), [](const Entry &e) { return e.state == QLatin1String("pending"); }));
    if (pending >= MaxPending) {
        return JsonRpc::RpcResult::fail(JsonRpc::makeError(JsonRpc::Busy, QStringLiteral("busy"),
                                                           QStringLiteral("%1 confirmations are already waiting for the user").arg(pending)));
    }

    const double fps = pCore->getCurrentFps();
    KdenliveDoc *doc = pCore->currentDoc();
    const QString project = doc->url().isEmpty() ? QStringLiteral("(chưa lưu)") : doc->url().fileName();
    QString text = QStringLiteral("AI muốn xuất video. File chỉ được ghi khi bạn bấm \"Xuất\".\n\n"
                                  "Project: %1\nFile: %2\nĐoạn: %3 – %4 (dài %5)\nKiểu xuất: %6\nMã hoá: %7")
                       .arg(project, QDir::toNativeSeparators(info.absoluteFilePath()), timecode(start, fps), timecode(end, fps),
                            timecode(end - start, fps), Presets.value(preset), Encoders.value(encoder));
    if (overwrite && info.exists()) {
        text += QStringLiteral("\n\n⚠ GHI ĐÈ file đang có ở đường dẫn trên.");
    }
    auto *box = new QMessageBox(QMessageBox::Question, QStringLiteral("ContextCut — AI muốn xuất video"), text, QMessageBox::NoButton, pCore->window());
    box->setWindowModality(Qt::NonModal);
    box->setAttribute(Qt::WA_DeleteOnClose);
    QPushButton *accept = box->addButton(QStringLiteral("Xuất"), QMessageBox::AcceptRole);
    QPushButton *reject = box->addButton(QStringLiteral("Không xuất"), QMessageBox::RejectRole);
    box->setDefaultButton(reject);
    box->setEscapeButton(reject);
    accept->setEnabled(false);
    QTimer::singleShot(ArmDelayMs, accept, [accept]() { accept->setEnabled(true); });

    const QString id = QStringLiteral("c-") + QUuid::createUuid().toString(QUuid::WithoutBraces);
    Entry entry;
    entry.box = box;
    entry.doc = doc;
    remember(id, entry);
    QObject::connect(box, &QDialog::finished, bridge, [bridge, id, box, accept]() {
        const bool sameProject = s_entries.value(id).doc == pCore->currentDoc();
        answer(bridge, id,
               !sameProject                       ? QStringLiteral("cancelled")
                   : box->clickedButton() == accept ? QStringLiteral("accepted")
                                                    : QStringLiteral("rejected"));
    });
    // Closing the project (opening another one, quitting) withdraws the question
    QObject::connect(doc, &QObject::destroyed, box, [id, box]() {
        answer(nullptr, id, QStringLiteral("cancelled"));
        box->close();
    });
    QTimer::singleShot(ExpireMs, box, [bridge, id, box]() {
        answer(bridge, id, QStringLiteral("expired"));
        box->close();
    });
    box->show();
    box->raise();
    box->activateWindow();
    QApplication::alert(pCore->window());
    qCInfo(CC_CONFIRM) << "confirmation" << id << "asked: export" << info.absoluteFilePath() << start << end << preset << encoder << overwrite;
    QJsonObject result = view(id, s_entries.value(id));
    result.insert(QStringLiteral("revision"), bridge->revisions()->current());
    return JsonRpc::RpcResult::ok(result);
}

JsonRpc::RpcResult lookup(const QJsonObject &params, QString &id)
{
    id = params.value(QLatin1String("confirm_id")).toString();
    if (!s_entries.contains(id)) {
        return JsonRpc::RpcResult::fail(
            JsonRpc::notFound(params.value(QLatin1String("confirm_id")), QStringLiteral("unknown confirm_id (forgotten when the app restarts)")));
    }
    return JsonRpc::RpcResult::ok(view(id, s_entries.value(id)));
}

JsonRpc::RpcResult cancel(AiBridgeServer *bridge, const QJsonObject &params)
{
    QString id;
    const JsonRpc::RpcResult found = lookup(params, id);
    if (found.error) {
        return found;
    }
    answer(bridge, id, QStringLiteral("cancelled"));
    if (QPointer<QMessageBox> box = s_entries.value(id).box) {
        box->close();
    }
    return JsonRpc::RpcResult::ok(view(id, s_entries.value(id)));
}

} // namespace

void registerMethods(AiBridgeServer &server)
{
    AiBridgeServer *bridge = &server;
    server.registerMethod(QStringLiteral("request_confirmation"), [bridge](const QJsonObject &params) { return request(bridge, params); });
    server.registerMethod(QStringLiteral("get_confirmation"), [](const QJsonObject &params) {
        QString id;
        return lookup(params, id);
    });
    server.registerMethod(QStringLiteral("cancel_confirmation"), [bridge](const QJsonObject &params) { return cancel(bridge, params); });
}

} // namespace ContextCut::Confirmations
