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
        <div ref={reactFlowWrapper} className="w-full h-full bg-white rounded-[32px] overflow-hidden border border-slate-200 group relative shadow-inner">
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
                className="bg-slate-50"
            >
                <Background color="#cbd5e1" gap={20} variant={BackgroundVariant.Dots} size={1} />
                <MiniMap
                    position="bottom-right"
                    style={{
                        background: '#ffffff',
                        border: '1px solid #e2e8f0',
                        borderRadius: '20px',
                        overflow: 'hidden',
                        width: 150,
                        height: 100,
                        boxShadow: '0 4px 12px rgba(0,0,0,0.05)'
                    }}
                    nodeColor={(n) => {
                        if (n.type === 'start') return '#22c55e';
                        if (n.type === 'end') return '#ef4444';
                        if (n.type === 'condition') return '#a855f7';
                        return '#3b82f6';
                    }}
                    maskColor="rgba(241, 245, 249, 0.6)"
                />
                <Controls
                    className="!bg-white !border-slate-200 !rounded-2xl overflow-hidden shadow-xl !flex !flex-col !gap-1 !p-1"
                    showInteractive={false}
                />
                <Panel position="top-right" className="flex gap-2">
                    <button
                        onClick={() => fitView()}
                        className="p-2.5 bg-white border border-slate-200 rounded-xl text-slate-400 hover:text-slate-900 hover:bg-slate-50 transition-all shadow-sm active:scale-95"
                        title="Fit View"
                    >
                        <Maximize2 size={18} strokeWidth={2.5} />
                    </button>
                    {selectedNode && selectedNode.type !== "start" && (
                        <button
                            onClick={handleDeleteSelected}
                            className="flex items-center gap-2 px-5 py-2.5 bg-red-50 text-red-600 border border-red-100 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-red-600 hover:text-white transition-all shadow-sm active:scale-95"
                        >
                            <Trash2 size={16} strokeWidth={2.5} /> Delete
                        </button>
                    )}
                    <button
                        onClick={handleSave}
                        className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-blue-700 transition-all shadow-[0_4px_12px_rgba(37,99,235,0.2)] active:scale-95 border border-blue-500"
                    >
                        <Save size={16} strokeWidth={2.5} /> Save Flow
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
