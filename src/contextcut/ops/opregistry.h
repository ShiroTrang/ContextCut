/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QJsonObject>
#include <QJsonValue>
#include <QList>
#include <QString>
#include <QStringList>

namespace ContextCut {

enum class ParamType { Frame, Int, Number, String, Enum, Bool, Track, Clip, Source };

/** @brief One parameter of an op, as published by list_operations (docs/protocol.md §8.5). */
struct ParamSpec
{
    QString name;
    ParamType type;
    bool required;
    QString description;
    /** @brief Value range for numbers, length range for strings; max 0 means unbounded */
    double min{0};
    double max{0};
    QStringList values;
    /** @brief Filled in when the parameter is absent */
    QJsonValue defaultValue{QJsonValue::Undefined};
};

struct OpSpec
{
    QString type;
    QString summary;
    QList<ParamSpec> params;
};

/** @brief The catalogue of AI timeline operations. */
namespace OpRegistry {

const QList<OpSpec> &specs();
const OpSpec *find(const QString &type);
/** @brief Result of the list_operations method */
QJsonObject listOperations();

} // namespace OpRegistry

} // namespace ContextCut
