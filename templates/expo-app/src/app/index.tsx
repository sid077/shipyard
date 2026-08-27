import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { track } from '@/analytics';
import { firstMeteredFeature } from '@/config/monetization';
import { product } from '@/config/product';
import { useEntitlement } from '@/purchases/entitlements';
import { spacing, useTheme } from '@/theme';
import { Button, Card, EmptyState, ListRow, Skeleton, Stack, Text } from '@/ui';

/**
 * The starter home screen. It demonstrates the gating pattern and the design
 * system every generated screen follows, and the first ticket replaces it.
 *
 * Real features name their feature key literally - `useEntitlement('export')`.
 * This screen derives one only so the template stays coherent for whichever
 * monetization plan the pipeline applies.
 */
const GATED_FEATURE = firstMeteredFeature() ?? 'unmetered';

export default function HomeScreen() {
  const theme = useTheme();
  const [items, setItems] = useState<string[]>([]);
  const { allowed, reason, remaining, recordUse } = useEntitlement(GATED_FEATURE);

  async function addItem() {
    // Ask before acting: `recordUse` spends the free allowance and tells us
    // whether this use was permitted at all.
    const permitted = await recordUse();
    if (!permitted) {
      track({ name: 'paywall_view', properties: { placement: 'home', trigger: GATED_FEATURE } });
      router.push('/paywall');
      return;
    }
    setItems((current) => {
      const next = [...current, `Item ${current.length + 1}`];
      if (next.length === 1) {
        track({ name: 'activation', properties: { feature: GATED_FEATURE } });
      }
      return next;
    });
  }

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text variant="body" tone="muted">
          {product.tagline}
        </Text>

        <Card>
          <Stack gap={2}>
            <Text testID="quota-label" variant="caption" tone="muted">
              {reason === 'loading'
                ? 'Checking your plan'
                : reason === 'entitled'
                  ? 'Pro — unlimited'
                  : remaining === null
                    ? 'Locked'
                    : `${remaining} left on the free plan`}
            </Text>

            {reason === 'loading' ? (
              <Skeleton variant="row" testID="quota-skeleton" />
            ) : items.length === 0 ? (
              <EmptyState
                testID="home-empty"
                title="Nothing here yet"
                body="Add your first item to get started."
              />
            ) : (
              items.map((item, index) => (
                <ListRow key={item} title={item} subtitle={`Added ${index + 1}`} />
              ))
            )}
          </Stack>
        </Card>

        <Button
          testID="add-item"
          label={allowed || reason === 'loading' ? 'Add item' : 'Unlock to add more'}
          onPress={addItem}
          haptic
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: spacing(5), gap: spacing(4) },
});
