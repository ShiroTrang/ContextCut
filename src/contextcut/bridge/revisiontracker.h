/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QList>
#include <QObject>
#include <QPointer>
#include <QUuid>
#include <memory>

class KdenliveDoc;
class QUndoStack;
class TimelineItemModel;

namespace ContextCut {

/** @class RevisionTracker
    @brief Counter that changes whenever the open timeline may have changed (docs/protocol.md §6).

    Bumped by the document undo stack (any edit, undo or redo, by the user or the AI), by structural changes of the
    active timeline model, and by switching project or sequence. Selection, playhead and view changes do not count.
    Starts at a random value so revisions from a previous launch never match.
 */
class RevisionTracker : public QObject
{
    Q_OBJECT
public:
    explicit RevisionTracker(QObject *parent = nullptr);
    /** @brief Re-binds to the current document/timeline if they changed, then returns the revision. */
    qint64 current();
    /** @brief Re-binds to the current document, undo stack and active timeline; bumps when any of them changed. */
    void sync();

private:
    void bump();
    qint64 m_revision;
    QPointer<KdenliveDoc> m_doc;
    QPointer<QUndoStack> m_undoStack;
    std::weak_ptr<TimelineItemModel> m_timeline;
    QUuid m_timelineUuid;
    QList<QMetaObject::Connection> m_connections;
};

} // namespace ContextCut
