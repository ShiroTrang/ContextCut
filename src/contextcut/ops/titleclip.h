/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "undohelper.hpp"

#include <QSize>
#include <QString>

namespace ContextCut {

enum class TitleStyle { CardBlack, CardDim, CaptionBottom, CaptionTop, CaptionPop };

/** @brief Text clips for title_card and caption: standard Kdenlive title clips (kdenlivetitle producer + xmldata), so stock Kdenlive
    opens and edits them in its titler. */
namespace TitleClip {

/** @brief kdenlivetitle document: centred text in Segoe UI bold, sized and placed for @p style on a @p frame sized canvas;
    @p color (#RRGGBB) replaces the style's text colour. */
QString xml(const QString &text, TitleStyle style, QSize frame, int duration, const QString &color = QString());

/** @brief Adds a title clip of @p duration frames to the bin root. The producer is built here, so the clip is ready at once and
    can be inserted in the same batch (ClipCreator::createTitleClip loads it asynchronously instead). */
bool addToBin(const QString &xml, int duration, const QString &name, QString &binId, Fun &undo, Fun &redo);

} // namespace TitleClip

} // namespace ContextCut
