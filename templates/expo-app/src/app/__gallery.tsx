import { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import {
  Badge,
  Button,
  Card,
  Divider,
  EmptyState,
  ErrorState,
  Input,
  ListRow,
  SegmentedControl,
  Skeleton,
  Spinner,
  Stack,
  Text,
} from '@/ui';
import { spacing, typeScale, useTheme } from '@/theme';

/**
 * Every component in every state, on one route.
 *
 * This is what the design-QA stage photographs: it exercises the whole system
 * without depending on product code, so a regression in a primitive is caught
 * even when no screen happens to use it.
 */
export default function GalleryScreen() {
  const theme = useTheme();
  const [text, setText] = useState('');
  const [segment, setSegment] = useState('all');

  return (
    <ScrollView
      testID="gallery"
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
    >
      <Section title="Type">
        {(Object.keys(typeScale) as (keyof typeof typeScale)[]).map((variant) => (
          <Text key={variant} variant={variant}>
            {variant} — {typeScale[variant].size}/{typeScale[variant].lineHeight}
          </Text>
        ))}
        <Text tone="muted">muted body</Text>
      </Section>

      <Section title="Buttons">
        <Button testID="g-primary" label="Primary" onPress={() => {}} />
        <Button testID="g-secondary" label="Secondary" variant="secondary" onPress={() => {}} />
        <Button testID="g-ghost" label="Ghost" variant="ghost" onPress={() => {}} />
        <Button testID="g-danger" label="Danger" variant="danger" onPress={() => {}} />
        <Button testID="g-disabled" label="Disabled" disabled onPress={() => {}} />
        <Button testID="g-loading" label="Loading" loading onPress={() => {}} />
        <Button testID="g-large" label="Large" size="lg" onPress={() => {}} />
      </Section>

      <Section title="Cards and rows">
        <Card>
          <Text>Flat card</Text>
        </Card>
        <Card variant="raised">
          <Text>Raised card</Text>
        </Card>
        <ListRow title="Dinner at Luca's" subtitle="4 people" trailing="$24.50" />
        <ListRow
          testID="g-row-pressable"
          title="Pressable row"
          subtitle="with a subtitle"
          trailing="›"
          onPress={() => {}}
        />
        <Divider />
      </Section>

      <Section title="Input">
        <Input label="Amount" value={text} onChangeText={setText} placeholder="0.00" />
        <Input label="With error" value="abc" onChangeText={() => {}} error="Enter a number." />
      </Section>

      <Section title="Selection">
        <SegmentedControl
          testID="g-segments"
          options={[
            { value: 'all', label: 'All' },
            { value: 'mine', label: 'Mine' },
          ]}
          value={segment}
          onChange={setSegment}
        />
        <Stack direction="row" gap={2} wrap>
          <Badge label="Neutral" />
          <Badge label="Primary" tone="primary" />
          <Badge label="Success" tone="success" />
          <Badge label="Danger" tone="danger" />
        </Stack>
      </Section>

      <Section title="Loading">
        <Skeleton variant="row" />
        <Skeleton variant="line" />
        <Spinner label="Loading" />
      </Section>

      <Section title="States">
        <EmptyState
          testID="g-empty"
          title="No splits yet"
          body="Your first one lands here."
          actionLabel="Add a split"
          onAction={() => {}}
        />
        <ErrorState
          testID="g-error"
          title="That did not save"
          body="Nothing was lost. Try again."
          retryLabel="Try again"
          onRetry={() => {}}
        />
      </Section>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text variant="caption" tone="muted" accessibilityRole="header">
        {title.toUpperCase()}
      </Text>
      <Stack gap={3}>{children}</Stack>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing(5), gap: spacing(7) },
  section: { gap: spacing(3) },
});
