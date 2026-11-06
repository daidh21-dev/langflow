import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import { cn } from "@/utils/utils";
import type { Deployment } from "../types";
import DeploymentStepsTracker from "./deployment-steps-tracker";

type DeploymentPhase = "deploying" | "deployed";

interface StepDeployStatusProps {
  phase: DeploymentPhase;
  deployment?: Deployment | null;
  deploymentName?: string;
  loadingTitle?: string;
  loadingDescription?: string;
  doneTitle?: string;
  doneDescription?: string;
  runKey?: number;
  onAllStepsComplete?: () => void;
  onRerunSteps?: () => void;
  showTestButton?: boolean;
  onTestDeployment?: () => void;
}

export default function StepDeployStatus({
  phase,
  deployment,
  deploymentName,
  loadingTitle,
  loadingDescription,
  doneTitle,
  doneDescription,
  runKey = 0,
  onAllStepsComplete,
  onRerunSteps,
  showTestButton = false,
  onTestDeployment,
}: StepDeployStatusProps) {
  const { t } = useTranslation();
  const isDeploying = phase === "deploying";

  const resolvedLoadingTitle =
    loadingTitle ??
    "Đang thực thi & kiểm tra từng bước triển khai lên AWS AgentCore...";
  const resolvedLoadingDescription =
    loadingDescription ??
    (deploymentName
      ? `Đang đồng bộ và kiểm tra trạng thái các bước cho "${deploymentName}"`
      : t("deployments.deployingDescription"));
  const resolvedDoneTitle =
    doneTitle ?? "Hoàn tất 5/5 bước triển khai & kiểm tra trạng thái!";
  const resolvedDoneDescription =
    doneDescription ??
    (deploymentName
      ? `Bản triển khai "${deploymentName}" đã vượt qua toàn bộ 5 bước kiểm tra và đang hoạt động (READY) trên AWS Bedrock AgentCore Runtime.`
      : t("deployments.deploymentLive"));

  return (
    <div className="flex flex-1 flex-col items-center justify-start gap-4 py-4">
      <div className="flex items-center gap-4 rounded-lg border border-border bg-muted/20 px-5 py-3.5 w-full max-w-3xl">
        <div className="relative flex shrink-0 items-center justify-center">
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-full transition-colors duration-500",
              isDeploying ? "bg-accent-indigo/10" : "bg-accent-emerald/15",
            )}
          >
            {isDeploying ? (
              <Loading size={26} className="text-accent-indigo-foreground" />
            ) : (
              <ForwardedIconComponent
                name="CircleCheck"
                className="h-7 w-7 text-emerald-500 animate-in zoom-in-50 duration-300"
              />
            )}
          </div>
          {isDeploying && (
            <div className="absolute h-12 w-12 animate-ping rounded-full bg-accent-indigo/10" />
          )}
        </div>

        <div className="flex flex-1 flex-col gap-0.5 text-left">
          <h3 className="text-base font-semibold text-foreground">
            {isDeploying ? resolvedLoadingTitle : resolvedDoneTitle}
          </h3>
          <p className="text-xs text-muted-foreground">
            {isDeploying ? resolvedLoadingDescription : resolvedDoneDescription}
          </p>
        </div>

        {!isDeploying && (
          <div className="flex shrink-0 items-center gap-2">
            {onRerunSteps && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs"
                onClick={onRerunSteps}
                data-testid="rerun-deploy-steps-btn"
              >
                <ForwardedIconComponent name="RotateCw" className="h-3.5 w-3.5" />
                Chạy lại từng bước
              </Button>
            )}
            {showTestButton && onTestDeployment && (
              <Button
                variant="default"
                size="sm"
                className="gap-1.5 text-xs"
                onClick={onTestDeployment}
                data-testid="deployment-stepper-test"
              >
                <ForwardedIconComponent name="Play" className="h-3.5 w-3.5" />
                {t("deployments.testDeployment")}
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="w-full max-w-3xl">
        <DeploymentStepsTracker
          deployment={deployment}
          isSimulatingProgress={isDeploying}
          compact={false}
          runKey={runKey}
          onAllStepsComplete={onAllStepsComplete}
        />
      </div>
    </div>
  );
}
