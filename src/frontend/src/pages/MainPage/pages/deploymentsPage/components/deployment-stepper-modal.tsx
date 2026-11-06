import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { usePostProviderAccount } from "@/controllers/API/queries/deployment-provider-accounts/use-post-provider-account";
import { useGetDeployment } from "@/controllers/API/queries/deployments/use-get-deployment";
import { useGetDeploymentAttachments } from "@/controllers/API/queries/deployments/use-get-deployment-attachments";
import { usePatchDeployment } from "@/controllers/API/queries/deployments/use-patch-deployment";
import { usePostDeployment } from "@/controllers/API/queries/deployments/use-post-deployment";
import useFlowStore from "@/stores/flowStore";
import { useFolderStore } from "@/stores/foldersStore";
import {
  DeploymentStepperProvider,
  useDeploymentStepper,
} from "../contexts/deployment-stepper-context";
import { isDeploymentUpdatePayloadEmpty } from "../helpers/deployment-payload-builders";
import { useErrorAlert } from "../hooks/use-error-alert";
import {
  DEFAULT_FLOW_NAME,
  type Deployment,
  type DeploymentProvider,
  getDeploymentDisplayName,
  getSelectedFlowVersionKey,
  type ProviderAccount,
  type SelectedFlowVersion,
} from "../types";
import DeploymentStepper, {
  CREATE_DEPLOYED_STEPS,
  EDIT_DEPLOYED_STEPS,
  EDIT_STEPS,
} from "./deployment-stepper";
import DeploymentStepperFooter from "./deployment-stepper-footer";
import DeploymentSuccessContent from "./deployment-success-content";
import StepAttachFlows from "./step-attach-flows";
import StepDeployStatus from "./step-deploy-status";
import StepProvider from "./step-provider";
import StepReview from "./step-review";
import StepType from "./step-type";

interface DeploymentStepperModalProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  onTestDeployment?: (
    deployment: { id: string; name: string },
    providerId: string,
  ) => void;
  initialFlowId?: string;
  initialVersionByFlow?: Map<string, SelectedFlowVersion>;
  initialProvider?: DeploymentProvider;
  initialInstance?: ProviderAccount;
  /** When provided, the modal opens in edit mode. */
  editingDeployment?: Deployment | null;
}

export default function DeploymentStepperModal({
  open,
  setOpen,
  onTestDeployment,
  initialFlowId,
  initialVersionByFlow,
  initialProvider,
  initialInstance,
  editingDeployment,
}: DeploymentStepperModalProps) {
  const { t } = useTranslation();
  const [isDeploying, setIsDeploying] = useState(false);
  const isEditMode = !!editingDeployment;
  const { folderId } = useParams();
  const myCollectionId = useFolderStore((state) => state.myCollectionId);
  const currentFlowProjectId = useFlowStore(
    (state) => state.currentFlow?.folder_id,
  );
  const resolvedProjectId =
    currentFlowProjectId ?? folderId ?? myCollectionId ?? undefined;

  // Edit mode: fetch existing attachments and deployment detail for LLM.
  const { data: attachmentsData, isLoading: isLoadingAttachments } =
    useGetDeploymentAttachments(
      { deploymentId: editingDeployment?.id ?? "" },
      { enabled: open && isEditMode && !!editingDeployment?.id },
    );
  const { data: deploymentDetail, isLoading: isLoadingDetail } =
    useGetDeployment(
      { deploymentId: editingDeployment?.id ?? "" },
      { enabled: open && isEditMode && !!editingDeployment?.id },
    );

  const editInitialState = useMemo(() => {
    if (!isEditMode || !attachmentsData?.flow_versions) return null;

    const versionMap = new Map<string, SelectedFlowVersion>();
    const toolNames = new Map<string, string>();
    const connectionsByFlow = new Map<string, string[]>();

    for (const fv of attachmentsData.flow_versions) {
      const key = getSelectedFlowVersionKey(fv.flow_id, fv.id);
      versionMap.set(key, {
        key,
        flowId: fv.flow_id,
        flowName: fv.flow_name ?? DEFAULT_FLOW_NAME,
        versionId: fv.id,
        versionTag: `v${fv.version_number}`,
      });
      const providerToolName = fv.provider_data?.tool_display_name;
      if (providerToolName) {
        toolNames.set(key, providerToolName);
      }
      const appIds = fv.provider_data?.app_ids;
      if (appIds && appIds.length > 0) {
        connectionsByFlow.set(key, appIds);
      }
    }

    const llm =
      typeof deploymentDetail?.provider_data?.llm === "string"
        ? deploymentDetail.provider_data.llm
        : "";

    return { versionMap, llm, toolNames, connectionsByFlow };
  }, [isEditMode, attachmentsData, deploymentDetail]);

  const isLoadingEditData =
    isEditMode && (isLoadingAttachments || isLoadingDetail);

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value && isDeploying) return;
        setOpen(value);
      }}
    >
      <DialogContent
        className="flex h-[85vh] w-[900px] !max-w-none flex-col gap-0 overflow-hidden border-none bg-transparent p-0 shadow-none"
        hideCloseButton
        hideTitle
        hideDescription
        overlayClassName="bg-black/30 dark:bg-black/50 backdrop-blur"
      >
        <DeploymentStepperProvider
          key={`${open}-${editingDeployment?.id ?? ""}-${initialProvider?.id ?? ""}-${initialInstance?.id ?? ""}-${isLoadingEditData}`}
          initialState={{
            projectId: resolvedProjectId,
            initialFlowId,
            selectedVersionByFlow:
              initialVersionByFlow ?? editInitialState?.versionMap,
            initialProvider,
            initialInstance,
            initialStep: isEditMode
              ? 1
              : initialProvider && initialInstance
                ? 2
                : 1,
            editingDeployment: editingDeployment ?? undefined,
            initialLlm: editInitialState?.llm,
            initialToolNameByFlow: editInitialState?.toolNames,
            initialConnectionsByFlow: editInitialState?.connectionsByFlow,
          }}
        >
          {isLoadingEditData ? (
            <>
              <DialogTitle className="sr-only">
                {t("deployments.loadingDeploymentData")}
              </DialogTitle>
              <div className="flex flex-1 items-center justify-center">
                <span className="text-sm text-muted-foreground">
                  {t("deployments.loadingDeploymentData")}
                </span>
              </div>
            </>
          ) : (
            <DeploymentStepperModalContent
              setOpen={setOpen}
              onTestDeployment={onTestDeployment}
              onDeployingChange={setIsDeploying}
            />
          )}
        </DeploymentStepperProvider>
      </DialogContent>
    </Dialog>
  );
}

type DeploymentPhase = "idle" | "deploying" | "deployed";

function DeploymentStepperModalContent({
  setOpen,
  onTestDeployment,
  onDeployingChange,
}: {
  setOpen: (open: boolean) => void;
  onTestDeployment?: (
    deployment: { id: string; name: string },
    providerId: string,
  ) => void;
  onDeployingChange: (isDeploying: boolean) => void;
}) {
  const [deploymentPhase, setDeploymentPhase] =
    useState<DeploymentPhase>("idle");
  const [createdDeployment, setCreatedDeployment] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [stepRunKey, setStepRunKey] = useState(0);
  const [isApiDone, setIsApiDone] = useState(false);
  const [isStepsDone, setIsStepsDone] = useState(false);

  const {
    isEditMode,
    editingDeployment,
    currentStep,
    totalSteps,
    minStep,
    canGoNext,
    handleNext,
    handleBack,
    selectedProvider,
    selectedInstance,
    setSelectedInstance,
    deploymentName,
    deploymentDescription,
    needsProviderAccountCreation,
    buildProviderAccountPayload,
    buildDeploymentPayload,
    buildDeploymentUpdatePayload,
  } = useDeploymentStepper();

  const { t } = useTranslation();
  const showError = useErrorAlert();

  const { mutateAsync: createProviderAccount } = usePostProviderAccount();
  const { mutateAsync: createDeployment } = usePostDeployment();
  const { mutateAsync: updateDeployment } = usePatchDeployment();

  const [isCreatingAccount, setIsCreatingAccount] = useState(false);

  const isDeploying = deploymentPhase === "deploying";
  const isDeployed = deploymentPhase === "deployed";
  const isInDeployPhase = isDeploying || isDeployed;
  const providerConsoleUrl =
    selectedInstance?.provider_key === "agentcore-runtime"
      ? "https://ap-southeast-1.console.aws.amazon.com/bedrock/home?region=ap-southeast-1"
      : "https://www.ibm.com/products/watsonx-orchestrate";
  const providerDisplayName =
    selectedProvider?.name ??
    (selectedInstance?.provider_key === "agentcore-runtime"
      ? "AgentCore Runtime"
      : "watsonx Orchestrate");

  // Transition from "deploying" to "deployed" only after BOTH the API call
  // AND all 5 sequential steps have finished running.
  useEffect(() => {
    if (deploymentPhase === "deploying" && isApiDone && isStepsDone) {
      setDeploymentPhase("deployed");
      onDeployingChange(false);
    }
  }, [deploymentPhase, isApiDone, isStepsDone, onDeployingChange]);

  const effectiveDeployment = useMemo<Deployment | null>(() => {
    if (editingDeployment) {
      return {
        ...editingDeployment,
        name: deploymentName || editingDeployment.name,
        description: deploymentDescription || editingDeployment.description,
      };
    }
    return {
      id: createdDeployment?.id ?? "",
      name: createdDeployment?.name ?? deploymentName,
      description: deploymentDescription,
    } as Deployment;
  }, [
    editingDeployment,
    createdDeployment,
    deploymentName,
    deploymentDescription,
  ]);

  // In edit mode, steps are shifted: 1=Type, 2=Attach, 3=Review.
  const logicalStep = isEditMode ? currentStep + 1 : currentStep;
  const isProviderStep = !isEditMode && currentStep === 1;
  const isFinalStep = currentStep === totalSteps;

  const handleStepNext = async () => {
    if (isProviderStep && needsProviderAccountCreation) {
      const accountPayload = buildProviderAccountPayload();
      if (!accountPayload) return;
      try {
        setIsCreatingAccount(true);
        const newAccount = await createProviderAccount(accountPayload);
        setSelectedInstance(newAccount);
      } catch (err: unknown) {
        showError(t("deployments.failedToCreateProviderAccount"), err);
        return;
      } finally {
        setIsCreatingAccount(false);
      }
    }
    handleNext();
  };

  const handleDeploy = async () => {
    try {
      setIsApiDone(false);
      setIsStepsDone(false);
      setStepRunKey((k) => k + 1);
      setDeploymentPhase("deploying");
      onDeployingChange(true);

      if (isEditMode) {
        const payload = buildDeploymentUpdatePayload();
        if (!isDeploymentUpdatePayloadEmpty(payload)) {
          await updateDeployment(payload);
        }
        if (editingDeployment) {
          setCreatedDeployment({
            id: editingDeployment.id,
            name:
              deploymentName.trim() ||
              getDeploymentDisplayName(editingDeployment),
          });
        }
        // Stay on the Deploy Status screen while the 5 steps complete!
        setIsApiDone(true);
        return;
      }

      const providerId = selectedInstance?.id;
      if (!providerId) {
        setDeploymentPhase("idle");
        onDeployingChange(false);
        return;
      }

      const payload = buildDeploymentPayload(providerId);
      const result = await createDeployment(payload);
      if (result && typeof result === "object" && "id" in result) {
        const deployment = result as Deployment;
        setCreatedDeployment({
          id: String(result.id),
          name: getDeploymentDisplayName(deployment),
        });
      }
      setIsApiDone(true);
    } catch (err: unknown) {
      setDeploymentPhase("idle");
      onDeployingChange(false);
      showError(
        isEditMode
          ? t("deployments.failedToUpdateDeployment")
          : t("deployments.failedToCreateDeployment"),
        err,
      );
    }
  };

  const handleRerunSteps = () => {
    setIsStepsDone(false);
    setIsApiDone(true);
    setStepRunKey((k) => k + 1);
    setDeploymentPhase("deploying");
    onDeployingChange(true);
  };

  const handleFooterBack = () => {
    if (isInDeployPhase) {
      setDeploymentPhase("idle");
      onDeployingChange(false);
      return;
    }
    handleBack();
  };

  const handleTest = () => {
    const targetDeployment =
      createdDeployment ??
      (editingDeployment
        ? {
            id: editingDeployment.id,
            name:
              deploymentName.trim() ||
              getDeploymentDisplayName(editingDeployment),
          }
        : null);
    const providerId =
      selectedInstance?.id ?? editingDeployment?.provider_id ?? "";
    if (!targetDeployment || !providerId) return;
    onTestDeployment?.(targetDeployment, providerId);
    setOpen(false);
  };

  const actionLabel = isEditMode
    ? t("deployments.update")
    : t("deployments.deploy");
  const actionIcon = isEditMode ? "Save" : "Rocket";
  const progressLabel = isEditMode
    ? t("deployments.updating")
    : t("deployments.deploying");

  return (
    <>
      <DialogTitle className="sr-only">
        {isEditMode
          ? t("deployments.updateDeployment")
          : t("deployments.createNewDeploymentTitle")}
      </DialogTitle>
      <DialogDescription className="sr-only">
        {t("deployments.stepOf", { current: currentStep, total: totalSteps })}
      </DialogDescription>

      {/* Title + Stepper */}
      <div className="flex flex-col gap-4 px-6 pt-6">
        <h2
          className="text-center text-2xl font-semibold"
          data-testid="stepper-modal-title"
        >
          {isDeployed && !isEditMode
            ? t("deployments.deployed")
            : isEditMode
              ? t("deployments.updateDeployment")
              : t("deployments.createNewDeploymentTitle")}
        </h2>
        <DeploymentStepper
          steps={
            isEditMode
              ? isDeployed
                ? EDIT_DEPLOYED_STEPS
                : EDIT_STEPS
              : isDeployed
                ? CREATE_DEPLOYED_STEPS
                : undefined
          }
          currentStepOverride={isInDeployPhase ? 4 : undefined}
          onStepClick={
            isEditMode && !isDeploying
              ? (stepNumber) => {
                  if (stepNumber === 4 && !isInDeployPhase) {
                    void handleDeploy();
                  } else if (stepNumber < 4 && isInDeployPhase) {
                    setDeploymentPhase("idle");
                  }
                }
              : undefined
          }
        />
      </div>

      {/* Content box: step content + footer */}
      <div className="mx-4 mb-4 mt-4 flex flex-1 flex-col overflow-hidden rounded-lg border border-border bg-background">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6 py-2">
          {isInDeployPhase ? (
            isDeployed && !isEditMode ? (
              <DeploymentSuccessContent
                deployment={effectiveDeployment}
                deploymentName={createdDeployment?.name}
                providerName={providerDisplayName}
                providerUrl={providerConsoleUrl}
                showTestButton={
                  !!onTestDeployment &&
                  !!createdDeployment &&
                  !!selectedInstance?.id
                }
                onTest={handleTest}
              />
            ) : (
              <StepDeployStatus
                phase={isDeploying ? "deploying" : "deployed"}
                deployment={effectiveDeployment}
                deploymentName={
                  createdDeployment?.name ??
                  (deploymentName.trim() ||
                    getDeploymentDisplayName(editingDeployment))
                }
                runKey={stepRunKey}
                onAllStepsComplete={() => setIsStepsDone(true)}
                onRerunSteps={handleRerunSteps}
                showTestButton={!!onTestDeployment}
                onTestDeployment={handleTest}
              />
            )
          ) : (
            <>
              {logicalStep === 1 && <StepProvider />}
              {logicalStep === 2 && <StepType />}
              {logicalStep === 3 && <StepAttachFlows />}
              {logicalStep === 4 && <StepReview />}
            </>
          )}
        </div>

        <DeploymentStepperFooter
          canGoNext={canGoNext}
          currentStep={currentStep}
          isCreatingAccount={isCreatingAccount}
          isDeployed={isDeployed}
          isDeploying={isDeploying}
          isInDeployPhase={isInDeployPhase}
          isFinalStep={isFinalStep}
          minStep={minStep}
          actionIcon={actionIcon}
          actionLabel={actionLabel}
          progressLabel={progressLabel}
          onBack={handleFooterBack}
          onCancel={() => setOpen(false)}
          onClose={() => setOpen(false)}
          onPrimaryAction={isFinalStep ? handleDeploy : handleStepNext}
        />
      </div>
    </>
  );
}
