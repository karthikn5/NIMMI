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
import { Trash2, Maximize2 } from "lucide-react";
import { FlowChecks, FlowTemplates } from "./FlowAssist";
import { checkFlow } from "./flowKit";

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
import HandoverNode from "./nodes/HandoverNode";

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
    const { screenToFlowPosition, fitView, setCenter } = useReactFlow();

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
            handover: HandoverNode,
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
    const issues = useMemo(() => checkFlow(nodes, edges), [nodes, edges]);
    const empty = nodes.length <= 1;

    // Jump to a block from the checks list, and open its settings.
    const focusNode = useCallback((nodeId: string) => {
        const n = nodes.find((x) => x.id === nodeId);
        if (!n) return;
        setCenter(n.position.x + 128, n.position.y + 60, { zoom: 1, duration: 400 });
        setSelectedNode(n);
        onNodeSelect(n);
        onNodesChange(nodes.map((x) => ({ type: "select" as const, id: x.id, selected: x.id === nodeId })));
    }, [nodes, setCenter, onNodeSelect, onNodesChange]);

    const applyTemplate = useCallback((flow: { nodes: Node[]; edges: Edge[] }) => {
        onSave(flow.nodes, flow.edges);
        setTimeout(() => fitView({ padding: 0.2, duration: 400 }), 50);
    }, [onSave, fitView]);

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

    const handleDeleteSelected = () => {
        if (selectedNode) {
            onNodesChange([{ type: 'remove', id: selectedNode.id }]);
            onEdgesChange(edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
                .map((e) => ({ type: 'remove' as const, id: e.id })));
            setSelectedNode(null);
            onNodeSelect(null);
        }
    };

    return (
        <div ref={reactFlowWrapper} className="w-full h-full bg-white rounded-lg overflow-hidden border border-line group relative">
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
                className="bg-[#fbfaf8]"
            >
                <Background color="#d6d1ca" gap={20} variant={BackgroundVariant.Dots} size={1} />
                <MiniMap
                    position="bottom-right"
                    style={{
                        background: '#ffffff',
                        border: '1px solid #e8e5e0',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        width: 150,
                        height: 100,
                        boxShadow: 'none'
                    }}
                    nodeColor={(n) => {
                        if (n.type === 'start') return '#550a64';
                        return '#a8a29e';
                    }}
                    maskColor="rgba(241, 245, 249, 0.6)"
                />
                <Controls
                    className="!bg-white !border !border-line !rounded-md overflow-hidden !shadow-none"
                    showInteractive={false}
                />
                {!empty && (
                    <Panel position="top-left">
                        <FlowChecks issues={issues} onPick={focusNode} />
                    </Panel>
                )}
                {empty && (
                    <Panel position="top-center" className="!mt-24">
                        <FlowTemplates onUse={applyTemplate} />
                    </Panel>
                )}
                <Panel position="top-right" className="flex gap-2">
                    {selectedNode && selectedNode.type !== "start" && (
                        <button
                            onClick={handleDeleteSelected}
                            className="inline-flex items-center gap-1.5 h-8 px-3 bg-white border border-line-strong rounded-md text-[13px] text-signal hover:bg-red-50 hover:border-red-200"
                        >
                            <Trash2 size={14} /> Delete block
                        </button>
                    )}
                    <button
                        onClick={() => fitView({ padding: 0.2 })}
                        className="inline-flex items-center gap-1.5 h-8 px-3 bg-white border border-line-strong rounded-md text-[13px] text-stone-600 hover:text-ink hover:bg-stone-50"
                        title="Fit the whole flow on screen"
                    >
                        <Maximize2 size={14} /> Fit
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
        case "handover":
            return { label: "Human Handover", message: "Please wait while I connect you to a human agent." };
        case "end":
            return { label: "End", message: "Thank you for your response!" };
        default:
            return { label: "Node" };
    }
}
