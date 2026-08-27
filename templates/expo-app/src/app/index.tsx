import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { track } from '@/analytics';
import { Button } from '@/components/button';
import { firstMeteredFeature } from '@/config/monetization';
import { product } from '@/config/product';
import { useEntitlement } from '@/purchases/entitlements';
import { radius, spacing, useTheme } from '@/theme';

/**
 * The starter home screen. It demonstrates the gating pattern every feature in
 * a generated app follows, and the first ticket replaces it.
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
      track({
        name: 'paywall_view',
        properties: { placement: 'home', trigger: GATED_FEATURE },
      });
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
        <Text style={[styles.tagline, { color: theme.muted }]}>{product.tagline}</Text>

        <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <Text testID="quota-label" style={[styles.quota, { color: theme.text }]}>
            {reason === 'loading'
              ? 'Checking your plan...'
              : reason === 'entitled'
                ? 'Pro - unlimited'
                : remaining === null
                  ? 'Locked'
                  : `${remaining} left on the free plan`}
          </Text>
          {items.length === 0 ? (
            <Text style={[styles.empty, { color: theme.muted }]}>
              Nothing here yet. Add your first item to get started.
            </Text>
          ) : (
            items.map((item) => (
              <Text key={item} style={[styles.item, { color: theme.text }]}>
                {item}
              </Text>
            ))
          )}
        </View>

        <Button
          testID="add-item"
          label={allowed || reason === 'loading' ? 'Add item' : 'Unlock to add more'}
          onPress={addItem}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: spacing(5), gap: spacing(4) },
  tagline: { fontSize: 15 },
  card: {
    borderRadius: radius,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing(4),
    gap: spacing(2),
  },
  quota: { fontSize: 13, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 },
  empty: { fontSize: 15, lineHeight: 22 },
  item: { fontSize: 16 },
});
