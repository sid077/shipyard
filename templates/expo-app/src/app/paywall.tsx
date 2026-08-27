import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { track } from '@/analytics';
import { Button } from '@/components/button';
import { headlinePrice, monetization } from '@/config/monetization';
import { reportError } from '@/observability';
import { useEntitlements } from '@/purchases/entitlements';
import { radius, spacing, useTheme } from '@/theme';

export default function PaywallScreen() {
  const theme = useTheme();
  const { purchase, restore, purchasesAvailable } = useEntitlements();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const price = headlinePrice();

  useEffect(() => {
    track({
      name: 'paywall_view',
      properties: {
        placement: monetization.paywall_placement[0] ?? 'unknown',
        trigger: monetization.paywall_trigger,
      },
    });
  }, []);

  const features = Object.values(monetization.entitlements).flat();
  const periodLabel =
    price.period === 'lifetime'
      ? 'one-time'
      : price.period === 'consumable'
        ? 'per pack'
        : `per ${price.period}`;

  async function run(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      reportError(caught, { where: 'PaywallScreen' });
      setError(failure);
    } finally {
      setBusy(false);
    }
  }

  function dismiss() {
    track({
      name: 'paywall_dismissed',
      properties: { placement: monetization.paywall_placement[0] ?? 'unknown' },
    });
    router.back();
  }

  return (
    <View style={[styles.screen, { backgroundColor: theme.background }]} testID="paywall">
      <View style={styles.body}>
        <Text style={[styles.headline, { color: theme.text }]}>{price.display_name}</Text>
        <Text testID="paywall-price" style={[styles.price, { color: theme.primary }]}>
          ${price.price_usd.toFixed(2)} {periodLabel}
        </Text>
        {monetization.trial_days > 0 ? (
          <Text style={[styles.trial, { color: theme.muted }]}>
            Free for {monetization.trial_days} days, then ${price.price_usd.toFixed(2)}.
          </Text>
        ) : null}

        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          {features.map((feature) => (
            <Text key={feature} style={[styles.feature, { color: theme.text }]}>
              {feature.replace(/_/g, ' ')}
            </Text>
          ))}
        </View>

        {!purchasesAvailable ? (
          <Text testID="paywall-unavailable" style={[styles.error, { color: theme.muted }]}>
            Purchases are not available on this build.
          </Text>
        ) : null}
        {error ? (
          <Text testID="paywall-error" style={[styles.error, { color: theme.danger }]}>
            {error}
          </Text>
        ) : null}
      </View>

      <View style={styles.actions}>
        {busy ? <ActivityIndicator color={theme.primary} /> : null}
        <Button
          testID="paywall-buy"
          label={`Unlock ${price.display_name}`}
          disabled={busy || !purchasesAvailable}
          onPress={() =>
            run(async () => {
              const ok = await purchase(price.sku);
              if (ok) router.back();
              else setError('That purchase did not complete.');
            }, 'That purchase did not complete.')
          }
        />
        <Button
          testID="paywall-restore"
          label="Restore purchases"
          variant="secondary"
          disabled={busy || !purchasesAvailable}
          onPress={() => run(restore, 'We could not restore your purchases.')}
        />
        <Button testID="paywall-dismiss" label="Not now" variant="secondary" onPress={dismiss} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: spacing(5), justifyContent: 'space-between' },
  body: { gap: spacing(3), paddingTop: spacing(6) },
  headline: { fontSize: 28, fontWeight: '700' },
  price: { fontSize: 20, fontWeight: '600' },
  trial: { fontSize: 15 },
  card: {
    borderRadius: radius,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing(4),
    gap: spacing(2),
  },
  feature: { fontSize: 16, textTransform: 'capitalize' },
  error: { fontSize: 14 },
  actions: { gap: spacing(3), paddingBottom: spacing(4) },
});
