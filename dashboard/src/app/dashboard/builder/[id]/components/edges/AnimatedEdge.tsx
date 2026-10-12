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
                style={{ ...style, strokeWidth: 1.5, stroke: "#b8b1a9" }}
                className="react-flow__edge-path"
                d={edgePath}
                markerEnd={markerEnd}
            />
            <path d={edgePath} fill="none" stroke="#550a64" strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="4 8" className="react-flow__edge-path">
                <animate attributeName="stroke-dashoffset" from="48" to="0" dur="2.4s" repeatCount="indefinite" />
            </path>
        </>
    );
}
