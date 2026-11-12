import { useState } from 'react';

import { Wordmark } from '@/components/Wordmark';
import { ThemeToggle } from '@/components/ThemeToggle';
import { MockSignInDialog } from '@/components/MockSignInDialog';
import { useAuth } from '@/hooks/AuthContext';

export function AuthPage() {
  const { signInWithFabric, signInLocally, fabricAuthEnabled } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [mockDialogOpen, setMockDialogOpen] = useState(false);

  const handleFabricSignIn = async () => {
    setError(null);
    setIsLoading(true);

    try {
      await signInWithFabric();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to sign in with Fabric.'
      );
      setIsLoading(false);
    }
  };

  const handleMockSignIn = async (email: string) => {
    setError(null);
    setIsLoading(true);
    setMockDialogOpen(false);

    try {
      await signInLocally(email);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to sign in locally.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const msLogo = (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 21 21"
      className="mr-2"
    >
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );

  const handleSignIn = fabricAuthEnabled
    ? handleFabricSignIn
    : () => setMockDialogOpen(true);

  const buttonLabel = isLoading
    ? fabricAuthEnabled
      ? 'Opening Microsoft sign-in…'
      : 'Signing in…'
    : 'Sign in with Microsoft';

  return (
    <div className="flex min-h-screen flex-col">
      <header className="hair flex h-14 items-center justify-between border-b px-6">
        <Wordmark />
        <ThemeToggle />
      </header>

      <main className="flex flex-1 items-center px-6">
        <div className="mx-auto w-full max-w-[440px]">
          <h1 className="t-display text-[40px]">Sign in to the atlas</h1>
          <p className="t-muted mt-4 text-[14px]">
            The slides are stored in a Microsoft Fabric workspace. Use the Microsoft account you sign in
            to Fabric with.
          </p>
          <button
            type="button"
            onClick={handleSignIn}
            disabled={isLoading}
            className="btn btn-ink mt-8 h-11 w-full justify-center text-[13px]"
          >
            {msLogo}
            {buttonLabel}
          </button>
          {error && <p className="t-accent mt-3 text-[12px]">{error}</p>}
        </div>
      </main>

      <footer className="t-faint hair border-t px-6 py-4 text-[11px]">
        Images: TCGA Research Network, via the NCI Genomic Data Commons. Not for clinical use.
      </footer>

      {!fabricAuthEnabled && (
        <MockSignInDialog
          open={mockDialogOpen}
          onConfirm={handleMockSignIn}
          onCancel={() => setMockDialogOpen(false)}
        />
      )}
    </div>
  );
}
