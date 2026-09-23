import { Children } from 'react';
import { motion } from 'framer-motion';

const EASE = 'easeOut';

const pageVariants = {
  initial: {
    opacity: 0,
    y: 6,
  },
  in: {
    opacity: 1,
    y: 0,
  },
  out: {
    opacity: 0,
    y: -6,
  },
};

const pageTransition = {
  type: 'tween',
  ease: EASE,
  duration: 0.18,
};

/**
 * Route-level page transition (fade + slight vertical slide).
 * Pair with <AnimatePresence mode="wait"> at the router level.
 */
export const PageTransition = ({ children }) => {
  return (
    <motion.div
      initial="initial"
      animate="in"
      exit="out"
      variants={pageVariants}
      transition={pageTransition}
      style={{ height: '100%', width: '100%' }}
    >
      {children}
    </motion.div>
  );
};

/** Simple fade-in wrapper with optional delay. */
export const FadeIn = ({ children, delay = 0 }) => {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
};

/** Slide-in-from-left wrapper with optional delay. */
export const SlideIn = ({ children, delay = 0 }) => {
  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
};

const itemVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0 },
};

/**
 * Staggered reveal container — wraps each direct child in an animated item.
 *   <StaggerContainer staggerDelay={0.04}>
 *     <Card />
 *     <Card />
 *   </StaggerContainer>
 */
export const StaggerContainer = ({ children, staggerDelay = 0.04 }) => {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: staggerDelay,
      },
    },
  };

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      {Children.map(children, (child) => (
        <motion.div variants={itemVariants}>{child}</motion.div>
      ))}
    </motion.div>
  );
};

export default PageTransition;
