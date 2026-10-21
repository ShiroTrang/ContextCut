/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "revisiontracker.h"
#include "contextcut/model/editorreader.h"
#include "core.h"
#include "doc/docundostack.hpp"
#include "doc/kdenlivedoc.h"
#include "timeline2/model/timelineitemmodel.hpp"

#include <QRandomGenerator>

namespace ContextCut {

RevisionTracker::RevisionTracker(QObject *parent)
    : QObject(parent)
    , m_revision(QRandomGenerator::system()->bounded(1, 1 << 30))
{
}

qint64 RevisionTracker::current()
{
    sync();
    return m_revision;
}

void RevisionTracker::bump()
{
    ++m_revision;
}

void RevisionTracker::sync()
{
    KdenliveDoc *doc = pCore->guiReady() ? pCore->currentDoc() : nullptr;
    QUndoStack *undoStack = doc ? doc->commandStack().get() : nullptr;
    const std::shared_ptr<TimelineItemModel> timeline = doc ? EditorReader::currentTimeline() : nullptr;
    const QUuid timelineUuid = timeline ? timeline->uuid() : QUuid();
    // QPointer/weak_ptr are null once the old object is gone, so a new object at the same address still counts as a change
    if (doc == m_doc.data() && undoStack == m_undoStack.data() && timeline == m_timeline.lock() && timelineUuid == m_timelineUuid) {
        return;
    }
    for (const auto &connection : std::as_const(m_connections)) {
        disconnect(connection);
    }
    m_connections.clear();
    m_doc = doc;
    m_undoStack = undoStack;
    m_timeline = timeline;
    m_timelineUuid = timelineUuid;
    bump();
    if (undoStack) {
        m_connections << connect(undoStack, &QUndoStack::indexChanged, this, &RevisionTracker::bump);
    }
    if (timeline) {
        auto *model = timeline.get();
        m_connections << connect(model, &QAbstractItemModel::rowsInserted, this, &RevisionTracker::bump);
        m_connections << connect(model, &QAbstractItemModel::rowsRemoved, this, &RevisionTracker::bump);
        m_connections << connect(model, &QAbstractItemModel::rowsMoved, this, &RevisionTracker::bump);
        m_connections << connect(model, &QAbstractItemModel::modelReset, this, &RevisionTracker::bump);
    }
}

} // namespace ContextCut
