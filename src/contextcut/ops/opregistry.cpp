/*
    SPDX-FileCopyrightText: 2026 ContextCut contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "opregistry.h"

#include <QJsonArray>
#include <climits>

namespace ContextCut::OpRegistry {

namespace {

constexpr double MaxFrame = INT_MAX;

ParamSpec frame(const QString &name, bool required, const QString &description)
{
    return {name, ParamType::Frame, required, description, 0, MaxFrame};
}

ParamSpec text(const QString &name, bool required, int maxLength, const QString &description)
{
    return {name, ParamType::String, required, description, required ? 1.0 : 0.0, double(maxLength)};
}

ParamSpec track(const QString &name, bool required, const QString &description)
{
    return {name, ParamType::Track, required, description};
}

ParamSpec choice(const QString &name, const QStringList &values, const QString &description)
{
    ParamSpec spec{name, ParamType::Enum, false, description};
    spec.values = values;
    spec.defaultValue = values.first();
    return spec;
}

QList<OpSpec> buildSpecs()
{
    const ParamSpec reason = text(QStringLiteral("reason"), false, 500, QStringLiteral("One sentence: why this edit (shown to the user)"));
    const ParamSpec clipId{QStringLiteral("clip_id"), ParamType::Clip, true, QStringLiteral("Timeline clip id from get_timeline")};
    const ParamSpec source{QStringLiteral("source"), ParamType::Source, true, QStringLiteral("Bin clip id (string) from list_sources / list_recordings")};
    const QString textTrack = QStringLiteral("Video track for the text; default: the unlocked video track named Chữ/Text/Title, else the top video track");

    ParamSpec audio{QStringLiteral("audio"), ParamType::Bool, false, QStringLiteral("Also place the source's audio (default true)")};
    audio.defaultValue = true;
    ParamSpec audioStream{QStringLiteral("audio_stream"), ParamType::Int, false,
                          QStringLiteral("MLT audio stream index as in list_recordings audio_streams[].index; default: the clip's default stream"), 0,
                          1000};
    ParamSpec gain{QStringLiteral("gain_db"), ParamType::Number, false, QStringLiteral("Music volume change in dB, -60..20 (default 0)"), -60, 20};
    gain.defaultValue = 0;
    ParamSpec musicIn = frame(QStringLiteral("in_f"), false, QStringLiteral("First source frame used (default 0)"));
    musicIn.defaultValue = 0;

    return {
        {QStringLiteral("cut_range"),
         QStringLiteral("Remove [start_f, end_f) from every unlocked track and close the gap (ripple delete); guides after it move back when no "
                        "track is locked"),
         {frame(QStringLiteral("start_f"), true, QStringLiteral("First timeline frame removed")),
          frame(QStringLiteral("end_f"), true, QStringLiteral("First timeline frame kept after the cut (> start_f)")), reason}},
        {QStringLiteral("split"),
         QStringLiteral("Cut a clip (and its linked audio/video) in two at a timeline frame; created = the right-hand halves"),
         {clipId, frame(QStringLiteral("at_f"), true, QStringLiteral("Timeline frame strictly inside the clip")), reason}},
        {QStringLiteral("trim"),
         QStringLiteral("Move a clip's edges on the timeline (the source in point follows the left edge); linked audio/video with the same edge "
                        "follows"),
         {clipId, frame(QStringLiteral("start_f"), false, QStringLiteral("New left edge (timeline frame); default unchanged")),
          frame(QStringLiteral("end_f"), false, QStringLiteral("New right edge, exclusive; default unchanged")), reason}},
        {QStringLiteral("move"),
         QStringLiteral("Move a clip so it starts at at_f; its group (linked audio/video) moves by the same offset; the destination must be free"),
         {clipId, frame(QStringLiteral("at_f"), true, QStringLiteral("New start frame")),
          track(QStringLiteral("track"), false, QStringLiteral("Destination track, same kind as the clip; default unchanged")), reason}},
        {QStringLiteral("insert_clip"),
         QStringLiteral("Place source frames [in_f, out_f) at at_f into free space on a track (no ripple); on a video track the audio goes to "
                        "audio_track, linked; never asks to create tracks"),
         {source, frame(QStringLiteral("in_f"), true, QStringLiteral("First source frame (project fps)")),
          frame(QStringLiteral("out_f"), true, QStringLiteral("Source frame after the last one used (> in_f)")),
          track(QStringLiteral("track"), true, QStringLiteral("Video track (picture, plus audio below) or audio track (audio only)")),
          frame(QStringLiteral("at_f"), true, QStringLiteral("Timeline start frame")),
          track(QStringLiteral("audio_track"), false, QStringLiteral("Audio track for the sound; default: the audio track paired with track")),
          audioStream, audio, reason}},
        {QStringLiteral("add_music"),
         QStringLiteral("Place the audio of a source (music, SFX) at at_f on the music track, optionally with a volume change"),
         {source, frame(QStringLiteral("at_f"), true, QStringLiteral("Timeline start frame")), musicIn,
          frame(QStringLiteral("out_f"), false, QStringLiteral("Source frame after the last one used; default: end of the source")),
          track(QStringLiteral("track"), false, QStringLiteral("Audio track; default: the unlocked audio track named Nhạc/Nhạc/SFX/Music")), gain,
          reason}},
        {QStringLiteral("title_card"),
         QStringLiteral("Full-screen text card (new title clip in the bin): white text centred on black or dimmed background"),
         {text(QStringLiteral("text"), true, 200, QStringLiteral("Text, e.g. \"Trong lúc đó:\"; \\n for a new line")),
          frame(QStringLiteral("start_f"), true, QStringLiteral("Timeline start frame")),
          frame(QStringLiteral("end_f"), true, QStringLiteral("Timeline end frame, exclusive (> start_f)")), track(QStringLiteral("track"), false, textTrack),
          choice(QStringLiteral("style"), {QStringLiteral("black"), QStringLiteral("dim")}, QStringLiteral("black: opaque background; dim: video shows through")),
          reason}},
        {QStringLiteral("caption"),
         QStringLiteral("Short on-screen line (new title clip in the bin): white text with black outline at the bottom or top, or big yellow (pop)"),
         {text(QStringLiteral("text"), true, 300, QStringLiteral("Text; \\n for a new line")),
          frame(QStringLiteral("start_f"), true, QStringLiteral("Timeline start frame")),
          frame(QStringLiteral("end_f"), true, QStringLiteral("Timeline end frame, exclusive (> start_f)")),
          text(QStringLiteral("speaker"), false, 60, QStringLiteral("Prefixed as \"<speaker>: \"")), track(QStringLiteral("track"), false, textTrack),
          choice(QStringLiteral("style"), {QStringLiteral("bottom"), QStringLiteral("top"), QStringLiteral("pop")},
                 QStringLiteral("bottom/top: position; pop: big yellow text in the upper third")),
          reason}},
    };
}

QString typeName(ParamType type)
{
    switch (type) {
    case ParamType::Frame:
        return QStringLiteral("frame");
    case ParamType::Int:
        return QStringLiteral("int");
    case ParamType::Number:
        return QStringLiteral("number");
    case ParamType::String:
        return QStringLiteral("string");
    case ParamType::Enum:
        return QStringLiteral("enum");
    case ParamType::Bool:
        return QStringLiteral("bool");
    case ParamType::Track:
        return QStringLiteral("track");
    case ParamType::Clip:
        return QStringLiteral("clip");
    case ParamType::Source:
        return QStringLiteral("source");
    }
    return QString();
}

} // namespace

const QList<OpSpec> &specs()
{
    static const QList<OpSpec> all = buildSpecs();
    return all;
}

const OpSpec *find(const QString &type)
{
    for (const OpSpec &spec : specs()) {
        if (spec.type == type) {
            return &spec;
        }
    }
    return nullptr;
}

QJsonObject listOperations()
{
    QJsonArray ops;
    for (const OpSpec &spec : specs()) {
        QJsonObject params;
        for (const ParamSpec &param : spec.params) {
            QJsonObject entry{{QStringLiteral("type"), typeName(param.type)},
                              {QStringLiteral("required"), param.required},
                              {QStringLiteral("description"), param.description}};
            const bool lengthRange = param.type == ParamType::String;
            if (param.type == ParamType::Frame || param.type == ParamType::Int || param.type == ParamType::Number || lengthRange) {
                entry.insert(lengthRange ? QStringLiteral("min_length") : QStringLiteral("min"), param.min);
                if (param.max > 0) {
                    entry.insert(lengthRange ? QStringLiteral("max_length") : QStringLiteral("max"), param.max);
                }
            }
            if (!param.values.isEmpty()) {
                entry.insert(QStringLiteral("values"), QJsonArray::fromStringList(param.values));
            }
            if (!param.defaultValue.isUndefined()) {
                entry.insert(QStringLiteral("default"), param.defaultValue);
            }
            params.insert(param.name, entry);
        }
        ops.append(QJsonObject{{QStringLiteral("type"), spec.type}, {QStringLiteral("summary"), spec.summary}, {QStringLiteral("params"), params}});
    }
    return {{QStringLiteral("ops"), ops}};
}

} // namespace ContextCut::OpRegistry
