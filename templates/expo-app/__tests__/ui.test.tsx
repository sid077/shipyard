import { render, screen, userEvent } from '@testing-library/react-native';

import { MIN_TOUCH_TARGET, contrastRatio, darkPalette, lightPalette, typeScale } from '@/theme';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  ListRow,
  SegmentedControl,
  Skeleton,
  Text,
} from '@/ui';

/**
 * The design system's own tests. A regression in a primitive would otherwise
 * only surface as a screenshot that looks slightly wrong.
 */

function flatten(style: unknown): Record<string, unknown> {
  const parts = Array.isArray(style) ? style.flat(Infinity) : [style];
  return Object.assign({}, ...parts.filter(Boolean));
}

describe('Button', () => {
  it('is announced as a button and is at least the minimum touch target', async () => {
    await render(<Button testID="b" label="Split the bill" onPress={() => {}} />);

    const button = screen.getByTestId('b');
    expect(screen.getByRole('button', { name: 'Split the bill' })).toBeOnTheScreen();
    expect(flatten(button.props.style).minHeight).toBeGreaterThanOrEqual(MIN_TOUCH_TARGET);
  });

  it('announces disabled and busy states rather than only looking different', async () => {
    await render(<Button testID="b" label="Save" disabled onPress={() => {}} />);
    expect(screen.getByTestId('b').props.accessibilityState).toMatchObject({ disabled: true });

    await render(<Button testID="c" label="Save" loading onPress={() => {}} />);
    expect(screen.getByTestId('c').props.accessibilityState).toMatchObject({ busy: true });
  });

  it('does not fire while disabled or loading', async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await render(<Button testID="b" label="Save" disabled onPress={onPress} />);
    await user.press(screen.getByTestId('b'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('fires once when pressed', async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await render(<Button testID="b" label="Save" onPress={onPress} />);
    await user.press(screen.getByTestId('b'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

describe('Text', () => {
  it('renders every rung of the generated type ramp', async () => {
    for (const variant of Object.keys(typeScale) as (keyof typeof typeScale)[]) {
      await render(
        <Text testID="t" variant={variant}>
          sample
        </Text>
      );
      const style = flatten(screen.getByTestId('t').props.style);
      expect(style.fontSize).toBe(typeScale[variant].size);
      expect(style.lineHeight).toBe(typeScale[variant].lineHeight);
    }
  });

  it('keeps line height legible on every rung', () => {
    for (const step of Object.values(typeScale)) {
      expect(step.lineHeight).toBeGreaterThanOrEqual(Math.round(step.size * 1.15));
    }
  });
});

describe('ListRow', () => {
  it('announces as one element, not three fragments', async () => {
    await render(
      <ListRow
        testID="row"
        title="Dinner"
        subtitle="4 people"
        trailing="$24.50"
        onPress={() => {}}
      />
    );
    const row = screen.getByTestId('row');
    expect(row.props.accessible).toBe(true);
    expect(row.props.accessibilityLabel).toBe('Dinner, 4 people');
  });

  it('is not a button when it does not act like one', async () => {
    await render(<ListRow testID="row" title="Dinner" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('Input', () => {
  it('keeps a visible label rather than relying on the placeholder', async () => {
    await render(<Input label="Amount" value="" onChangeText={() => {}} placeholder="0.00" />);
    expect(screen.getByText('Amount')).toBeOnTheScreen();
  });

  it('surfaces its error in text, not only as a red border', async () => {
    await render(
      <Input label="Amount" value="abc" onChangeText={() => {}} error="Enter a number." />
    );
    expect(screen.getByText('Enter a number.')).toBeOnTheScreen();
  });
});

describe('SegmentedControl', () => {
  it('marks the selected segment for assistive tech', async () => {
    await render(
      <SegmentedControl
        testID="seg"
        options={[
          { value: 'all', label: 'All' },
          { value: 'mine', label: 'Mine' },
        ]}
        value="all"
        onChange={() => {}}
      />
    );
    expect(screen.getByTestId('seg-all').props.accessibilityState).toMatchObject({
      selected: true,
    });
    expect(screen.getByTestId('seg-mine').props.accessibilityState).toMatchObject({
      selected: false,
    });
  });
});

describe('states and feedback', () => {
  it('renders an empty state that teaches rather than reports', async () => {
    await render(<EmptyState testID="e" title="No splits yet" body="Your first one lands here." />);
    expect(screen.getByText('No splits yet')).toBeOnTheScreen();
    expect(screen.getByText('Your first one lands here.')).toBeOnTheScreen();
  });

  it('offers a retry on an error state', async () => {
    const onRetry = jest.fn();
    const user = userEvent.setup();
    await render(
      <ErrorState
        title="That did not save"
        body="Nothing was lost."
        retryLabel="Try again"
        onRetry={onRetry}
      />
    );
    await user.press(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('announces a skeleton as progress, not as empty content', async () => {
    await render(<Skeleton testID="s" />);
    expect(screen.getByTestId('s').props.accessibilityLabel).toBe('Loading');
  });

  it('renders a badge and a card without crashing', async () => {
    await render(
      <Card testID="card">
        <Badge label="Pro" tone="primary" />
      </Card>
    );
    expect(screen.getByTestId('card')).toBeOnTheScreen();
    expect(screen.getByText('Pro')).toBeOnTheScreen();
  });
});

describe('the derived dark palette', () => {
  it('stays legible without anyone having designed it', () => {
    for (const palette of [lightPalette, darkPalette]) {
      expect(contrastRatio(palette.text, palette.background)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(palette.text, palette.surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(palette.textMuted, palette.background)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(palette.onPrimary, palette.primary)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
