import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing } from 'react-native';

import { motion } from '@/theme';

/**
 * Motion built on React Native's own `Animated`, not on a worklet runtime.
 *
 * The template keeps `react-native-reanimated` available for gesture-driven
 * product code, but the design system's own motion stays on `Animated` so it
 * needs no extra Jest configuration and cannot break the unit suite.
 */

export const easings = {
  standard: Easing.bezier(0.2, 0, 0, 1),
  decelerate: Easing.bezier(0, 0, 0, 1),
  accelerate: Easing.bezier(0.3, 0, 1, 1),
  emphasized: Easing.bezier(0.2, 0, 0, 1.2),
} as const;

export type EasingName = keyof typeof easings;

/**
 * Whether the viewer has asked for reduced motion.
 *
 * Honouring this is an accessibility requirement, not a preference: motion
 * triggers nausea in people with vestibular disorders.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((value) => {
        if (active) setReduced(value);
      })
      .catch(() => {});
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', (value) =>
      setReduced(value)
    );
    return () => {
      active = false;
      subscription?.remove();
    };
  }, []);

  return reduced;
}

/** A press-scale value for a touchable. Flat when reduced motion is on. */
export function usePressScale(depth = 0.97) {
  const reduced = useReducedMotion();
  // A lazy `useState` rather than `useRef(...).current`: reading a ref during
  // render is what the React Compiler rules forbid, and this is equally stable.
  const [scale] = useState(() => new Animated.Value(1));

  const to = (value: number) =>
    Animated.timing(scale, {
      toValue: reduced ? 1 : value,
      duration: motion.fast,
      easing: easings.standard,
      useNativeDriver: true,
    }).start();

  return {
    scale,
    onPressIn: () => to(depth),
    onPressOut: () => to(1),
  };
}

/** Fade a value in once on mount. Instant when reduced motion is on. */
export function useFadeIn(duration: number = motion.medium) {
  const reduced = useReducedMotion();
  const [opacity] = useState(() => new Animated.Value(0));

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: 1,
      duration: reduced ? 0 : duration,
      easing: easings.decelerate,
      useNativeDriver: true,
    }).start();
  }, [opacity, duration, reduced]);

  return opacity;
}
