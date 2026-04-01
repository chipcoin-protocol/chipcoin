import { useState } from "react";

import { ConfigureNode } from "./ConfigureNode";
import { CreateWallet } from "./CreateWallet";
import { ImportWallet } from "./ImportWallet";
import { RecoverWallet } from "./RecoverWallet";
import { SetPassword } from "./SetPassword";

type Step = "welcome" | "create" | "recover" | "import" | "password" | "node";
type Mode = "create-seed" | "recover-seed" | "import-key";

export function OnboardingApp(): JSX.Element {
  const [step, setStep] = useState<Step>("welcome");
  const [mode, setMode] = useState<Mode>("create-seed");
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [privateKeyHex, setPrivateKeyHex] = useState("");

  return (
    <main>
      <h1>Chipcoin Wallet Onboarding</h1>
      {step === "welcome" && (
        <section>
          <p>Create a new wallet, recover from a saved recovery phrase, or import a private key as a fallback. Secrets stay client-side.</p>
          <button onClick={() => { setMode("create-seed"); setStep("create"); }}>Create new wallet</button>
          <button onClick={() => { setMode("recover-seed"); setStep("recover"); }}>Recover wallet</button>
          <button onClick={() => { setMode("import-key"); setStep("import"); }}>Import private key</button>
        </section>
      )}
      {step === "create" && <CreateWallet onContinue={(value) => { setRecoveryPhrase(value); setStep("password"); }} />}
      {step === "recover" && <RecoverWallet onContinue={(value) => { setRecoveryPhrase(value); setStep("password"); }} />}
      {step === "import" && <ImportWallet onContinue={(value) => { setPrivateKeyHex(value); setStep("password"); }} />}
      {step === "password" && (
        <SetPassword
          mode={mode}
          recoveryPhrase={recoveryPhrase}
          privateKeyHex={privateKeyHex}
          onCreated={() => setStep("node")}
        />
      )}
      {step === "node" && <ConfigureNode />}
    </main>
  );
}
