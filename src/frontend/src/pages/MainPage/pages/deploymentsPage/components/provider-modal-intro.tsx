import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Badge } from "@/components/ui/badge";
import { decorateWxoUrl } from "@/utils/decorate-wxo-url";
import { cn } from "@/utils/utils";
import {
  AGENTCORE_PROVIDER_KEY,
  type ProviderAccount,
  WXO_PROVIDER_KEY,
} from "../types";

interface ProviderModalIntroProps {
  provider?: ProviderAccount | null;
  selectedProviderKey?: string;
  onSelectProviderKey?: (providerKey: string) => void;
}

export default function ProviderModalIntro({
  provider,
  selectedProviderKey,
  onSelectProviderKey,
}: ProviderModalIntroProps) {
  const { t } = useTranslation();
  const activeKey =
    provider?.provider_key ?? selectedProviderKey ?? AGENTCORE_PROVIDER_KEY;
  const isAgentCore = activeKey === AGENTCORE_PROVIDER_KEY;

  return (
    <div className="flex flex-col gap-3">
      {onSelectProviderKey ? (
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => onSelectProviderKey(AGENTCORE_PROVIDER_KEY)}
            className={cn(
              "flex items-center gap-2 rounded-lg border p-3 text-left transition-colors",
              isAgentCore
                ? "border-primary bg-primary/5"
                : "border-border bg-muted hover:border-foreground/30",
            )}
          >
            <ForwardedIconComponent
              name="Cpu"
              className="h-6 w-6 shrink-0 text-foreground"
            />
            <span className="text-sm font-medium">AgentCore Runtime</span>
          </button>
          <button
            type="button"
            onClick={() => onSelectProviderKey(WXO_PROVIDER_KEY)}
            className={cn(
              "flex items-center gap-2 rounded-lg border p-3 text-left transition-colors",
              !isAgentCore
                ? "border-primary bg-primary/5"
                : "border-border bg-muted hover:border-foreground/30",
            )}
          >
            <ForwardedIconComponent
              name="WatsonxOrchestrate"
              className="h-6 w-6 shrink-0 text-foreground"
            />
            <span className="text-sm font-medium">watsonx Orchestrate</span>
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-muted p-3">
          <ForwardedIconComponent
            name={isAgentCore ? "Cpu" : "WatsonxOrchestrate"}
            className="h-8 w-8 text-foreground"
          />
          <span className="text-sm font-medium">
            {isAgentCore ? "AgentCore Runtime" : "watsonx Orchestrate"}
          </span>
          <Badge
            variant={isAgentCore ? "emerald" : "purpleStatic"}
            size="xq"
            className="shrink-0"
          >
            {isAgentCore ? "Ready" : "Beta"}
          </Badge>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        {provider ? (
          t("deployments.updateEnvironmentDescription")
        ) : isAgentCore ? (
          "Nhập tên môi trường, URL endpoint (ví dụ: https://langflow.daido.dev hoặc AWS Bedrock AgentCore endpoint) và API Key để kết nối AgentCore Runtime."
        ) : (
          <>
            {t("deployments.wxoConfigureCredentials")}{" "}
            <a
              href={decorateWxoUrl(
                "https://www.ibm.com/products/watsonx-orchestrate#pricing",
                "signup-pricing",
              )}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary hover:underline"
            >
              {t("deployments.wxoSignUp")}
            </a>
            . {t("deployments.wxoAlreadyHaveAccount")}{" "}
            <a
              href={decorateWxoUrl(
                "https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=api-getting-started",
                "docs-credentials",
              )}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary hover:underline"
            >
              {t("deployments.wxoFindCredentials")}
            </a>
            .
          </>
        )}
      </p>
    </div>
  );
}
