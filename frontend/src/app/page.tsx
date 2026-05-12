"use client";

import React, { useMemo, useState } from "react";
import "./agentic-chat.css";
import "@copilotkit/react-core/v2/styles.css";
import {
  CopilotKit,
  CopilotChat,
  type ToolsMenuItem,
} from "@copilotkit/react-core/v2";
// import { CopilotChat } from "@copilotkit/react-ui";

const MODEL_STYLES = [
  "Normal",
  "Learning",
  "research",
  "explainatory",
] as const;

type ModelStyle = (typeof MODEL_STYLES)[number];

const AgenticChat: React.FC = () => {
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      showDevConsole={false}
      enableInspector={false}
      agent="default"
    >
      <Chat />
    </CopilotKit>
  );
};

const Chat = () => {
  const [modelStyle, setModelStyle] = useState<ModelStyle>("Normal");

  const toolsMenu = useMemo<(ToolsMenuItem | "-")[]>(() => {
    return [
      {
        label: "Model Style",
        items: MODEL_STYLES.map((style) => ({
          label: style === modelStyle ? `* ${style}` : style,
          action: () => setModelStyle(style),
        })),
      },
    ];
  }, [modelStyle]);

  return (
    <div className="h-screen w-screen bg-white flex flex-col">
      <div className="px-4 py-2 text-sm text-gray-600 border-b border-gray-200">
        Model Style: <span className="font-medium text-gray-900">{modelStyle}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CopilotChat
          agentId="default"
          className="h-full w-full"
          input={{ toolsMenu }}
        />
      </div>
    </div>
  );
};

export default AgenticChat;
