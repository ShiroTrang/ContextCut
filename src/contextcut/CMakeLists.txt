# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL

# ContextCut sources are compiled into kdenliveLib like the other src/ subfolders.
# Qt WebSockets is found and linked in src/CMakeLists.txt (block marked "ContextCut:").
set(kdenlive_SRCS
  ${kdenlive_SRCS}
  contextcut/bridge/aibridgeserver.cpp
  contextcut/bridge/jsonrpc.cpp
  contextcut/bridge/revisiontracker.cpp
  contextcut/model/editorreader.cpp
  contextcut/ops/batchapplier.cpp
  contextcut/ops/opregistry.cpp
  contextcut/ops/opvalidator.cpp
  contextcut/ops/timelineops.cpp
  contextcut/ops/titleclip.cpp
  PARENT_SCOPE)
