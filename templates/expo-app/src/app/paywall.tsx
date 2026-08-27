import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { track } from '@/analytics';
import { headlinePrice, monetization } from '@/config/monetization';
import { reportError } from '@/observability';
import { useEntitlements } from '@/purchases/entitlements';
import { spacing, useTheme } from '@/theme';
import { Button, Card, Stack, Text, haptics } from '@/ui';

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
      void haptics.error();
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
      <Stack gap={3} style={styles.body}>
        <Text variant="title">{price.display_name}</Text>
        <Text testID="paywall-price" variant="heading" tone="primary">
          ${price.price_usd.toFixed(2)} {periodLabel}
        </Text>
        {monetization.trial_days > 0 ? (
          <Text tone="muted">
            Free for {monetization.trial_days} days, then ${price.price_usd.toFixed(2)}.
          </Text>
        ) : null}

        <Card>
          <Stack gap={2}>
            {features.map((feature) => (
              <Text key={feature}>{feature.replace(/_/g, ' ')}</Text>
            ))}
          </Stack>
        </Card>

        {!purchasesAvailable ? (
          <Text testID="paywall-unavailable" variant="caption" tone="muted">
            Purchases are not available on this build.
          </Text>
        ) : null}
        {error ? (
          <Text testID="paywall-error" variant="caption" tone="danger">
            {error}
          </Text>
        ) : null}
      </Stack>

      <Stack gap={3} style={styles.actions}>
        <Button
          testID="paywall-buy"
          label={`Unlock ${price.display_name}`}
          size="lg"
          loading={busy}
          disabled={!purchasesAvailable}
          onPress={() =>
            run(async () => {
              const ok = await purchase(price.sku);
              if (ok) {
                await haptics.success();
                router.back();
              } else {
                setError('That purchase did not complete.');
              }
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
        <Button testID="paywall-dismiss" label="Not now" variant="ghost" onPress={dismiss} />
      </Stack>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: spacing(5), justifyContent: 'space-between' },
  body: { paddingTop: spacing(6) },
  actions: { paddingBottom: spacing(4) },
});
