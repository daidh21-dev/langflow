import { useEffect, useRef, useState } from "react";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Badge } from "@/components/ui/badge";
import Loading from "@/components/ui/loading";
import { cn } from "@/utils/utils";
import type { Deployment } from "../types";
import { getDeploymentDisplayName } from "../types";

export type StepState = "completed" | "in_progress" | "pending";

export interface DeploymentPipelineStep {
  stepNumber: number;
  title: string;
  description: string;
  technicalDetail: string;
  statusLabel: string;
  state: StepState;
}

export function buildPipelineStepsForDeployment(
  deployment?: Deployment | null,
  activeStepIndex?: number,
): DeploymentPipelineStep[] {
  const displayName = getDeploymentDisplayName(deployment ?? null);
  const desc = deployment?.description ?? "";
  const isMethod2 =
    displayName.toLowerCase().includes("cách 2") ||
    displayName.toLowerCase().includes("python graph") ||
    desc.toLowerCase().includes("method2");

  const rawSteps = isMethod2
    ? [
        {
          stepNumber: 1,
          title:
            "Bước 1 [Cách 2 - Code-First]: Biên dịch Đồ thị Python (agent_graph.py)",
          description:
            "Chuyển đổi luồng nghiệp vụ thành class đồ thị Python độc lập (LangflowPythonGraph), không cần đọc file JSON.",
          technicalDetail:
            "Mã nguồn: agent_graph.py + app.py (Code-First Python Graph)",
          doneLabel: "Đã biên dịch Python",
          activeLabel: "Đang biên dịch Python Graph...",
        },
        {
          stepNumber: 2,
          title:
            "Bước 2 [Cách 2]: Đóng gói Thư viện ARM64 & Đẩy lên S3 Artifact Store",
          description:
            "Đóng gói mã Python Graph cùng SDK bedrock_agentcore lên S3 CodeConfiguration.",
          technicalDetail:
            "s3://flow-vs-agentcore-code-095355901701-ap-southeast-1/langflow_demo/method2_python_graph/code.zip",
          doneLabel: "Đã tải lên S3",
          activeLabel: "Đang tải lên S3...",
        },
        {
          stepNumber: 3,
          title:
            "Bước 3 [Cách 2]: Khởi tạo AWS AgentCore Runtime (Chế độ Python Graph)",
          description:
            "Cấp phát MicroVM PYTHON_3_13 trên AWS Singapore, nạp trực tiếp module agent_graph.py vào bộ nhớ.",
          technicalDetail:
            "Runtime ID: langflow_method2_python_graph-f40S0AGoqe | Region: ap-southeast-1 | Entrypoint: app.py -> agent_graph.graph",
          doneLabel: "READY",
          activeLabel: "CREATING -> READY...",
        },
        {
          stepNumber: 4,
          title:
            "Bước 4 [Cách 2]: Kiểm tra Health Check (/ping) & Kết nối Bedrock Claude",
          description:
            "Xác nhận pipeline ChatInput -> PromptComponent -> BedrockClaudeConverse -> ChatOutput sẵn sàng.",
          technicalDetail:
            'GET /ping -> {"status": "Healthy"} | Model: anthropic.claude-3-haiku-20240307-v1:0',
          doneLabel: "Healthy (200 OK)",
          activeLabel: "Đang kiểm tra /ping...",
        },
        {
          stepNumber: 5,
          title:
            "Bước 5 [Cách 2]: Kích hoạt Cổng Thực thi Đồ thị Python (/invocations)",
          description:
            "Kết nối khung Test Chat trên UI Langflow thẳng tới hàm graph.run() trên AWS Bedrock AgentCore.",
          technicalDetail:
            "ARN: arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:runtime/langflow_method2_python_graph-f40S0AGoqe",
          doneLabel: "Đang hoạt động (Live)",
          activeLabel: "Đang kết nối cổng Chat...",
        },
      ]
    : [
        {
          stepNumber: 1,
          title:
            "Bước 1 [Inbound Gateway & Guardrail]: Xác thực Keycloak OIDC & Quét đồng bộ Guardrail v10",
          description:
            "Tiếp nhận yêu cầu qua Inbound Gateway (Custom JWT Authorizer - Keycloak OIDC) và quét đồng bộ Input + Output bằng Amazon Bedrock Guardrails.",
          technicalDetail:
            "Inbound GW: inbound-hr-gateway | Guardrail: ibfo21kotrmo (Version 10 - Input + Output sync scan)",
          doneLabel: "Verified & Protected",
          activeLabel: "Đang kiểm tra Gateway & Guardrail v10...",
        },
        {
          stepNumber: 2,
          title:
            "Bước 2 [AgentCore Memory]: Khởi tạo AgentCoreMemorySessionManager",
          description:
            "Đồng bộ phiên hội thoại ngắn hạn & dài hạn của nhân sự qua AgentCore Memory.",
          technicalDetail:
            "Memory ID: harness_hr_agent_test_1-EaQdhn7ACO | Manager: AgentCoreMemorySessionManager",
          doneLabel: "Memory Synced",
          activeLabel: "Đang nạp bộ nhớ phiên...",
        },
        {
          stepNumber: 3,
          title:
            "Bước 3 [Outbound RAG & Knowledge Base]: Kết nối MCP Gateway RAG & Bedrock Knowledge Base",
          description:
            "Ủy quyền qua AWS IAM SigV4 + Token Vault API Key tới Amazon Bedrock Knowledge Base (S3 + Vector Search).",
          technicalDetail:
            "Outbound RAG GW: gateway-retrieval-hr-agent-xcjlmpsg83 | Knowledge Base ID: RVAHZPCHQN",
          doneLabel: "RAG Ready",
          activeLabel: "Đang kết nối Knowledge Base RVAHZPCHQN...",
        },
        {
          stepNumber: 4,
          title:
            "Bước 4 [Outbound HR Ops & Cedar Policy]: Kết nối MCP Gateway HR Ops -> Kong API GW",
          description:
            "Kiểm tra chính sách phân quyền bằng Cedar Policy Engine trước khi định tuyến lệnh nghiệp vụ HR tới Kong API Gateway.",
          technicalDetail:
            "Outbound HR Ops GW: gateway-hr-operations | Policy: Cedar Policy Engine -> Kong API GW",
          doneLabel: "Policy Active",
          activeLabel: "Đang nạp Cedar Policy & Kong GW...",
        },
        {
          stepNumber: 5,
          title:
            "Bước 5 [AgentCore Harness & LLM]: Kích hoạt Strands Agents SDK (BedrockAgentCoreApp) & Claude Sonnet",
          description:
            "Thực thi điều phối HR Agent trên AWS Bedrock AgentCore Harness với mô hình Claude 3.5 Sonnet / Claude Sonnet.",
          technicalDetail:
            "Harness ARN: arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:harness/harness_hr_agent_test_1-XRpGABpNt4 | LLM: anthropic.claude-3-5-sonnet-20240620-v1:0 / global.anthropic.claude-sonnet-5",
          doneLabel: "READY (Live)",
          activeLabel: "Đang kích hoạt AgentCore Harness...",
        },
      ];

  return rawSteps.map((s, idx) => {
    let state: StepState = "completed";
    let statusLabel = s.doneLabel;

    if (typeof activeStepIndex === "number") {
      if (idx < activeStepIndex) {
        state = "completed";
        statusLabel = s.doneLabel;
      } else if (idx === activeStepIndex) {
        state = "in_progress";
        statusLabel = s.activeLabel;
      } else {
        state = "pending";
        statusLabel = "Đang chờ";
      }
    }

    return {
      stepNumber: s.stepNumber,
      title: s.title,
      description: s.description,
      technicalDetail: s.technicalDetail,
      statusLabel,
      state,
    };
  });
}

interface DeploymentStepsTrackerProps {
  deployment?: Deployment | null;
  isSimulatingProgress?: boolean;
  compact?: boolean;
  runKey?: number;
  onAllStepsComplete?: () => void;
}

export default function DeploymentStepsTracker({
  deployment,
  isSimulatingProgress = false,
  compact = false,
  runKey = 0,
  onAllStepsComplete,
}: DeploymentStepsTrackerProps) {
  const [activeIdx, setActiveIdx] = useState<number>(
    isSimulatingProgress ? 0 : 5,
  );
  const onCompleteRef = useRef(onAllStepsComplete);
  onCompleteRef.current = onAllStepsComplete;

  useEffect(() => {
    if (!isSimulatingProgress) {
      setActiveIdx(5);
      return;
    }
    setActiveIdx(0);
    const timer = setInterval(() => {
      setActiveIdx((prev) => {
        const next = prev + 1;
        if (next >= 5) {
          clearInterval(timer);
          setTimeout(() => {
            onCompleteRef.current?.();
          }, 250);
          return 5;
        }
        return next;
      });
    }, 1100);
    return () => clearInterval(timer);
  }, [isSimulatingProgress, runKey]);

  const steps = buildPipelineStepsForDeployment(
    deployment,
    isSimulatingProgress ? activeIdx : undefined,
  );

  const completedCount = steps.filter((s) => s.state === "completed").length;
  const progressPercent = Math.round((completedCount / steps.length) * 100);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4">
      <div className="flex flex-col gap-2 border-b border-border pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ForwardedIconComponent
              name="Activity"
              className="h-4 w-4 text-primary"
            />
            <span className="text-sm font-semibold text-foreground">
              Tiến trình & Trạng thái các bước triển khai (AWS Bedrock AgentCore Runtime)
            </span>
          </div>
          <Badge
            variant={
              isSimulatingProgress && completedCount < 5
                ? "secondaryStatic"
                : "emerald"
            }
            size="xq"
            className="gap-1.5"
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                isSimulatingProgress && completedCount < 5
                  ? "animate-pulse bg-amber-500"
                  : "bg-emerald-500",
              )}
            />
            {isSimulatingProgress && completedCount < 5
              ? `Đang chạy bước ${Math.min(activeIdx + 1, 5)}/5 (${progressPercent}%)`
              : "5/5 Bước Hoàn tất • READY (100%)"}
          </Badge>
        </div>

        {/* Progress Bar */}
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full transition-all duration-500",
              completedCount === 5 ? "bg-emerald-500" : "bg-primary",
            )}
            style={{
              width: `${isSimulatingProgress ? Math.max(progressPercent, activeIdx * 20 + 10) : 100}%`,
            }}
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {steps.map((step) => {
          const isCompleted = step.state === "completed";
          const isInProgress = step.state === "in_progress";

          return (
            <div
              key={step.stepNumber}
              className={cn(
                "flex items-start justify-between gap-3 rounded-md border px-3 py-2.5 transition-all duration-300",
                isCompleted && "border-emerald-500/25 bg-emerald-500/5",
                isInProgress &&
                  "border-primary/50 bg-primary/5 shadow-sm ring-1 ring-primary/20",
                step.state === "pending" &&
                  "border-border bg-muted/20 opacity-60",
              )}
            >
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 flex shrink-0 items-center justify-center">
                  {isCompleted ? (
                    <div className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                      <ForwardedIconComponent
                        name="Check"
                        className="h-3.5 w-3.5"
                      />
                    </div>
                  ) : isInProgress ? (
                    <div className="flex h-5 w-5 items-center justify-center">
                      <Loading size={16} className="text-primary" />
                    </div>
                  ) : (
                    <div className="flex h-5 w-5 items-center justify-center rounded-full border border-muted-foreground/40 text-xs text-muted-foreground">
                      {step.stepNumber}
                    </div>
                  )}
                </div>

                <div className="flex flex-col gap-0.5">
                  <span className="text-xs font-semibold text-foreground">
                    {step.title}
                  </span>
                  {!compact && (
                    <span className="text-xs text-muted-foreground">
                      {step.description}
                    </span>
                  )}
                  <code className="mt-0.5 rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {step.technicalDetail}
                  </code>
                </div>
              </div>

              <Badge
                variant={
                  isCompleted
                    ? "emerald"
                    : isInProgress
                      ? "purpleStatic"
                      : "secondaryStatic"
                }
                size="xq"
                className="shrink-0"
              >
                {step.statusLabel}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}
