/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "titleclip.h"
#include "bin/projectfolder.h"
#include "bin/projectitemmodel.h"
#include "core.h"

#include <QColor>
#include <QDomDocument>
#include <QFont>
#include <QFontMetricsF>
#include <cmath>
#include <mlt++/MltProducer.h>

namespace ContextCut::TitleClip {

namespace {

struct Look
{
    double sizeRatio;    // font pixel size / frame height
    QString color;       // "r,g,b,a" like TitleDocument::colorToString
    double outlineRatio; // outline width / font size, 0 = none
    int backgroundAlpha; // full-frame black rectangle, -1 = none
};

Look lookFor(TitleStyle style)
{
    switch (style) {
    case TitleStyle::CardBlack:
        return {0.085, QStringLiteral("255,255,255,255"), 0, 255};
    case TitleStyle::CardDim:
        return {0.085, QStringLiteral("255,255,255,255"), 0, 170};
    case TitleStyle::CaptionBottom:
    case TitleStyle::CaptionTop:
        return {0.055, QStringLiteral("255,255,255,255"), 0.08, -1};
    case TitleStyle::CaptionPop:
        return {0.075, QStringLiteral("255,221,0,255"), 0.09, -1};
    }
    return {0.055, QStringLiteral("255,255,255,255"), 0, -1};
}

QDomElement positioned(QDomDocument &doc, const QString &type, int z, double x, double y)
{
    QDomElement item = doc.createElement(QStringLiteral("item"));
    item.setAttribute(QStringLiteral("type"), type);
    item.setAttribute(QStringLiteral("z-index"), z);
    QDomElement position = doc.createElement(QStringLiteral("position"));
    position.setAttribute(QStringLiteral("x"), QString::number(x));
    position.setAttribute(QStringLiteral("y"), QString::number(y));
    QDomElement transform = doc.createElement(QStringLiteral("transform"));
    transform.appendChild(doc.createTextNode(QStringLiteral("1,0,0,0,1,0,0,0,1")));
    position.appendChild(transform);
    item.appendChild(position);
    return item;
}

} // namespace

QString xml(const QString &text, TitleStyle style, QSize frame, int duration, const QString &color)
{
    Look look = lookFor(style);
    if (const QColor custom(color); !color.isEmpty() && custom.isValid()) {
        look.color = QStringLiteral("%1,%2,%3,255").arg(custom.red()).arg(custom.green()).arg(custom.blue());
    }
    const int width = frame.width();
    const int height = frame.height();
    QFont font(QStringLiteral("Segoe UI"));
    font.setPixelSize(std::max(8, int(std::lround(height * look.sizeRatio))));
    font.setWeight(QFont::Bold);
    const double outline = look.outlineRatio > 0 ? std::max(2.0, font.pixelSize() * look.outlineRatio) : 0;

    // Measure like the titler would lay the text out, so the box can be centred
    const QFontMetricsF metrics(font);
    const QStringList lines = text.split(QLatin1Char('\n'));
    double boxWidth = 0;
    for (const QString &line : lines) {
        boxWidth = std::max(boxWidth, metrics.horizontalAdvance(line));
    }
    boxWidth = std::min(std::ceil(boxWidth + 2 * outline), double(width));
    const double boxHeight = std::ceil(metrics.lineSpacing() * lines.size() + 2 * outline);
    const double x = std::max(0.0, (width - boxWidth) / 2);
    double y = 0;
    switch (style) {
    case TitleStyle::CardBlack:
    case TitleStyle::CardDim:
        y = (height - boxHeight) / 2;
        break;
    case TitleStyle::CaptionBottom:
        y = height * 0.90 - boxHeight;
        break;
    case TitleStyle::CaptionTop:
        y = height * 0.08;
        break;
    case TitleStyle::CaptionPop:
        y = height * 0.30 - boxHeight / 2;
        break;
    }

    QDomDocument doc;
    QDomElement main = doc.createElement(QStringLiteral("kdenlivetitle"));
    main.setAttribute(QStringLiteral("width"), width);
    main.setAttribute(QStringLiteral("height"), height);
    main.setAttribute(QStringLiteral("LC_NUMERIC"), QStringLiteral("C"));
    main.setAttribute(QStringLiteral("duration"), duration);
    main.setAttribute(QStringLiteral("out"), duration);
    doc.appendChild(main);

    if (look.backgroundAlpha >= 0) {
        QDomElement rect = positioned(doc, QStringLiteral("QGraphicsRectItem"), 0, 0, 0);
        QDomElement content = doc.createElement(QStringLiteral("content"));
        content.setAttribute(QStringLiteral("rect"), QStringLiteral("0,0,%1,%2").arg(width).arg(height));
        content.setAttribute(QStringLiteral("pencolor"), QStringLiteral("0,0,0,0"));
        content.setAttribute(QStringLiteral("penwidth"), 0);
        content.setAttribute(QStringLiteral("brushcolor"), QStringLiteral("0,0,0,%1").arg(look.backgroundAlpha));
        rect.appendChild(content);
        main.appendChild(rect);
    }

    QDomElement item = positioned(doc, QStringLiteral("QGraphicsTextItem"), 1, x, y);
    QDomElement content = doc.createElement(QStringLiteral("content"));
    content.setAttribute(QStringLiteral("font"), font.family());
    content.setAttribute(QStringLiteral("font-weight"), int(font.weight()));
    content.setAttribute(QStringLiteral("font-pixel-size"), font.pixelSize());
    content.setAttribute(QStringLiteral("font-italic"), 0);
    content.setAttribute(QStringLiteral("font-underline"), 0);
    content.setAttribute(QStringLiteral("letter-spacing"), 0);
    content.setAttribute(QStringLiteral("box-width"), QString::number(boxWidth));
    content.setAttribute(QStringLiteral("box-height"), QString::number(boxHeight));
    content.setAttribute(QStringLiteral("alignment"), int(Qt::AlignHCenter));
    content.setAttribute(QStringLiteral("font-color"), look.color);
    if (outline > 0) {
        content.setAttribute(QStringLiteral("font-outline"), QString::number(outline));
        content.setAttribute(QStringLiteral("font-outline-color"), QStringLiteral("0,0,0,255"));
    }
    content.setAttribute(QStringLiteral("shadow"), QStringLiteral("0;#64000000;3;3;3"));
    content.setAttribute(QStringLiteral("typewriter"), QStringLiteral("0;2;0;0;0"));
    content.appendChild(doc.createTextNode(text));
    item.appendChild(content);
    main.appendChild(item);

    QDomElement startViewport = doc.createElement(QStringLiteral("startviewport"));
    startViewport.setAttribute(QStringLiteral("rect"), QStringLiteral("0,0,%1,%2").arg(width).arg(height));
    main.appendChild(startViewport);
    QDomElement endViewport = doc.createElement(QStringLiteral("endviewport"));
    endViewport.setAttribute(QStringLiteral("rect"), QStringLiteral("0,0,%1,%2").arg(width).arg(height));
    main.appendChild(endViewport);
    QDomElement background = doc.createElement(QStringLiteral("background"));
    background.setAttribute(QStringLiteral("color"), QStringLiteral("0,0,0,0"));
    main.appendChild(background);
    return doc.toString();
}

bool addToBin(const QString &xml, int duration, const QString &name, QString &binId, Fun &undo, Fun &redo)
{
    // Same properties ClipLoadTask sets on a title producer (case ClipType::Text)
    auto producer = std::make_shared<Mlt::Producer>(pCore->getProjectProfile(), nullptr, "kdenlivetitle:");
    if (!producer->is_valid()) {
        return false;
    }
    producer->set("xmldata", xml.toUtf8().constData());
    producer->set("length", duration);
    producer->set("out", duration - 1);
    producer->set("kdenlive:duration", producer->frames_to_time(duration));
    producer->set("kdenlive:clipname", name.toUtf8().constData());
    binId.clear();
    const auto model = pCore->projectItemModel();
    return model->requestAddBinClip(binId, producer, model->getRootFolder()->clipId(), undo, redo);
}

} // namespace ContextCut::TitleClip
