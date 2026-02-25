"use client";

import React from "react";
import { EdgeProps, getSmoothStepPath, EdgeLabelRenderer, getBezierPath } from "reactflow";

export default function AnimatedEdge({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style = {},
    markerEnd,
}: EdgeProps) {
    const [edgePath, labelX, labelY] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
    });

    return (
        <>
            <path
                id={id}
                style={{ ...style, strokeWidth: 3, stroke: "#3b82f633" }}
                className="react-flow__edge-path"
                d={edgePath}
                markerEnd={markerEnd}
            />
            <path
                d={edgePath}
                fill="none"
                stroke="#3b82f6"
                strokeWidth={2}
                strokeDasharray="5, 5"
                className="react-flow__edge-path"
            >
                <animate
                    attributeName="stroke-dashoffset"
                    from="100"
                    to="0"
                    dur="2s"
                    repeatCount="indefinite"
                />
            </path>
            {/* Gradient Glow */}
            <path
                d={edgePath}
                fill="none"
                stroke="#326cb5"
                strokeWidth={4}
                opacity={0.2}
                className="react-flow__edge-path"
            />
        </>
    );
}
