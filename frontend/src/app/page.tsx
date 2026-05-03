"use client";

import React from "react";
import "./agentic-chat.css";
import "@copilotkit/react-core/v2/styles.css";
import {
  CopilotKit,
  CopilotChat
} from "@copilotkit/react-core/v2";
// import { CopilotChat } from "@copilotkit/react-ui";

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
  return (
    <div className="h-screen w-screen bg-white flex flex-col">
      <div style={{ flex: 1, minHeight: 0 }}>
        <CopilotChat
          agentId="default"
          className="h-full w-full"
          />
        </div>
      </div>
  );
};

export default AgenticChat;
