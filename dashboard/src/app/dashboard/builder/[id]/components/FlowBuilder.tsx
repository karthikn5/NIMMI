"use client";

import { useState, useCallback, useMemo, useRef, DragEvent } from "react";
import ReactFlow, {
    Node,
    Edge,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    addEdge,
    Connection,
    ConnectionMode,
    Panel,
    MarkerType,
    NodeChange,
    EdgeChange,
    ReactFlowProvider,
    useReactFlow,
    MiniMap,
    BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";
import { Play, Save, Trash2, Maximize2, Minimize2 } from "lucide-react";

// Custom node types
import StartNode from "./nodes/StartNode";
import MessageNode from "./nodes/MessageNode";
import TextInputNode from "./nodes/TextInputNode";
import EmailInputNode from "./nodes/EmailInputNode";
import MultipleChoiceNode from "./nodes/MultipleChoiceNode";
import DatePickerNode from "./nodes/DatePickerNode";
import ConditionNode from "./nodes/ConditionNode";
import NumberInputNode from "./nodes/NumberInputNode";
import EndNode from "./nodes/EndNode";
import PhoneInputNode from "./nodes/PhoneInputNode";
import ImageNode from "./nodes/ImageNode";
import VideoNode from "./nodes/VideoNode";
import FileUploadNode from "./nodes/FileUploadNode";
import RatingNode from "./nodes/RatingNode";
import DelayNode from "./nodes/DelayNode";
import VariableNode from "./nodes/VariableNode";
import AiPromptNode from "./nodes/AiPromptNode";
import HttpRequestNode from "./nodes/HttpRequestNode";
import WebhookNode from "./nodes/WebhookNode";
import SlackNode from "./nodes/SlackNode";
import GoogleSheetsNode from "./nodes/GoogleSheetsNode";

// Custom edge types
import AnimatedEdge from "./edges/AnimatedEdge";

interface FlowBuilderProps {
    botId: string;
    nodes: Node[];
    edges: Edge[];
    onNodesChange: (changes: NodeChange[]) => void;
    onEdgesChange: (changes: EdgeChange[]) => void;
    onConnect: (params: Connection) => void;
    onSave: (nodes: Node[], edges: Edge[]) => void;
    onNodeSelect: (node: Node | null) => void;
}

function FlowBuilderInner({
    botId,
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onSave,
    onNodeSelect,
}: FlowBuilderProps) {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const { screenToFlowPosition, fitView } = useReactFlow();

    const nodeTypes = useMemo(
        () => ({
            start: StartNode,
            message: MessageNode,
            textInput: TextInputNode,
            emailInput: EmailInputNode,
            multipleChoice: MultipleChoiceNode,
            datePicker: DatePickerNode,
            condition: ConditionNode,
            numberInput: NumberInputNode,
            end: EndNode,
            phoneInput: PhoneInputNode,
            image: ImageNode,
            video: VideoNode,
            fileUpload: FileUploadNode,
            rating: RatingNode,
            delay: DelayNode,
            variable: VariableNode,
            aiPrompt: AiPromptNode,
            httpRequest: HttpRequestNode,
            webhook: WebhookNode,
            slack: SlackNode,
            googleSheets: GoogleSheetsNode,
        }),
        []
    );

    const edgeTypes = useMemo(
        () => ({
            animated: AnimatedEdge,
        }),
        []
    );

    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    // Filter out start node for deletion logic if needed
    // const canDelete = selectedNode && selectedNode.type !== "start";

    const onNodeClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            setSelectedNode(node);
            onNodeSelect(node);
        },
        [onNodeSelect]
    );

    const onPaneClick = useCallback(() => {
        setSelectedNode(null);
        onNodeSelect(null);
    }, [onNodeSelect]);

    const onDragOver = useCallback((event: DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
    }, []);

    const onDrop = useCallback(
        (event: DragEvent) => {
            event.preventDefault();

            const type = event.dataTransfer.getData("application/reactflow");
            if (!type) return;

            // Convert screen coordinates to flow coordinates
            const position = screenToFlowPosition({
                x: event.clientX,
                y: event.clientY,
            });

            const newNode: Node = {
                id: `${type}-${Date.now()}`,
                type,
                position,
                data: getDefaultNodeData(type),
            };

            // Notify parent to add node
            onNodesChange([{ type: 'add', item: newNode }]);
        },
        [screenToFlowPosition, onNodesChange]
    );

    const handleSave = () => {
        onSave(nodes, edges);
    };

    const handleDeleteSelected = () => {
        if (selectedNode) {
            onNodesChange([{ type: 'remove', id: selectedNode.id }]);
            setSelectedNode(null);
            onNodeSelect(null);
        }
    };

    return (
        <div ref={reactFlowWrapper} className="w-full h-full bg-[#0a0a0a] rounded-2xl overflow-hidden border border-white/10 group relative">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onDragOver={onDragOver}
                onDrop={onDrop}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                connectionMode={ConnectionMode.Loose}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                className="bg-[#0a0a0a]"
            >
                <Background color="#ffffff05" gap={20} variant={BackgroundVariant.Lines} />
                <MiniMap
                    position="bottom-right"
                    style={{
                        background: '#111',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '12px',
                        overflow: 'hidden',
                        width: 150,
                        height: 100
                    }}
                    nodeColor={(n) => {
                        if (n.type === 'start') return '#22c55e';
                        if (n.type === 'end') return '#ef4444';
                        if (n.type === 'condition') return '#a855f7';
                        return '#3b82f6';
                    }}
                    maskColor="rgba(0, 0, 0, 0.6)"
                />
                <Controls
                    className="!bg-zinc-900 !border-white/10 !rounded-xl overflow-hidden shadow-2xl"
                    showInteractive={false}
                />
                <Panel position="top-right" className="flex gap-2">
                    <button
                        onClick={() => fitView()}
                        className="p-2 bg-white/5 border border-white/10 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
                        title="Fit View"
                    >
                        <Maximize2 size={16} />
                    </button>
                    {selectedNode && selectedNode.type !== "start" && (
                        <button
                            onClick={handleDeleteSelected}
                            className="flex items-center gap-2 px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm font-bold hover:bg-red-500/30 transition-colors"
                        >
                            <Trash2 size={16} /> Delete
                        </button>
                    )}
                    <button
                        onClick={handleSave}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg text-sm font-bold hover:bg-blue-500 transition-colors shadow-lg shadow-blue-600/20"
                    >
                        <Save size={16} /> Save Flow
                    </button>
                </Panel>
            </ReactFlow>
        </div>
    );
}

// Wrap with provider to use useReactFlow hook
export default function FlowBuilder(props: FlowBuilderProps) {
    return (
        <ReactFlowProvider>
            <FlowBuilderInner {...props} />
        </ReactFlowProvider>
    );
}

function getDefaultNodeData(type: string) {
    switch (type) {
        case "start":
            return { label: "Start" };
        case "message":
            return { label: "Bot Message", message: "Hello! How can I help you?" };
        case "textInput":
            return { label: "Text Input", placeholder: "Enter your response...", required: true };
        case "emailInput":
            return { label: "Email Input", placeholder: "Enter your email...", required: true };
        case "phoneInput":
            return { label: "Phone Input", placeholder: "Enter phone number...", required: true };
        case "multipleChoice":
            return { label: "Multiple Choice", options: ["Option 1", "Option 2", "Option 3"], required: true };
        case "datePicker":
            return { label: "Date Picker", placeholder: "Select a date...", required: false };
        case "condition":
            return { label: "If Condition", variable: "", operator: "equals", value: "" };
        case "numberInput":
            return { label: "Number Input", placeholder: "Enter a number...", required: false };
        case "image":
            return { label: "Display Image", imageUrl: "" };
        case "video":
            return { label: "Embed Video", videoUrl: "" };
        case "fileUpload":
            return { label: "File Upload", placeholder: "Upload your documents", required: false };
        case "rating":
            return { label: "Star Rating", scale: 5 };
        case "delay":
            return { label: "Delay", delay: 2 };
        case "variable":
            return { label: "Set Variable", variableName: "", variableValue: "" };
        case "aiPrompt":
            return { label: "AI Logic Step", prompt: "" };
        case "httpRequest":
            return { label: "External API Call", url: "", method: "POST" };
        case "webhook":
            return { label: "External Webhook", url: "", method: "POST" };
        case "slack":
            return { label: "Slack Notification", url: "", channel: "#general" };
        case "googleSheets":
            return { label: "Sheets Sync", spreadsheetId: "", sheetName: "Sheet1" };
        case "end":
            return { label: "End", message: "Thank you for your response!" };
        default:
            return { label: "Node" };
    }
}
