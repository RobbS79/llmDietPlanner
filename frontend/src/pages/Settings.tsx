import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { fetchBillingMe, type BillingMe } from '@/lib/billing';
import type { Profile } from '@/lib/settings';
import { PreferencesSection } from '@/components/settings/PreferencesSection';
import { AccountSection } from '@/components/settings/AccountSection';

export const Settings = () => {
  const { data: profile, isLoading } = useQuery<Profile>({
    queryKey: ['profile'],
    queryFn: () => api.get('/auth/profile/').then(r => r.data.data),
  });
  const { data: billing } = useQuery<BillingMe>({ queryKey: ['billing-me'], queryFn: fetchBillingMe });

  if (isLoading || !profile) return <LoadingScreen message="Načítání…" />;

  return (
    <MainLayout>
      <div className="max-w-2xl mx-auto px-6 py-12 w-full space-y-8">
        <header>
          <h1 className="font-display text-3xl font-black text-ink tracking-tighter uppercase italic">
            Nastavení<span className="text-paprika not-italic">.</span>
          </h1>
          <p className="text-muted text-sm font-bold mt-2">Spravujte svůj účet a předvolby</p>
        </header>
        <PreferencesSection profile={profile} />
        <AccountSection profile={profile} />
        <SubscriptionSection billing={billing} />
        <PrivacySection profile={profile} />
        <DataSection />
      </div>
    </MainLayout>
  );
};

function SubscriptionSection({ billing }: { billing: BillingMe | undefined }) {
  void billing;
  return (
    <Card variant="paper" className="p-8">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight mb-4">Předplatné</h2>
    </Card>
  );
}

function PrivacySection({ profile }: { profile: Profile }) {
  void profile;
  return (
    <Card variant="paper" className="p-8">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight mb-4">Soukromí</h2>
    </Card>
  );
}

function DataSection() {
  return (
    <Card variant="paper" className="p-8">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight mb-4">Moje data</h2>
    </Card>
  );
}
