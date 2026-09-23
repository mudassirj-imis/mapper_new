import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { Alert, Slide, Snackbar } from '@mui/material';

const SnackbarContext = createContext(null);

/**
 * Snackbar notifications available app-wide via `useSnackbar()`.
 *
 *   const { showSnackbar } = useSnackbar();
 *   showSnackbar('Mapping saved', 'success');
 */
export function SnackbarProvider({ children }) {
  const [state, setState] = useState({
    open: false,
    message: '',
    severity: 'info',
    key: 0,
  });

  const showSnackbar = useCallback((message, severity = 'info') => {
    setState((prev) => ({
      open: true,
      message,
      severity,
      // Bump the key so consecutive notifications re-trigger the animation.
      key: prev.key + 1,
    }));
  }, []);

  const hideSnackbar = useCallback((_event, reason) => {
    if (reason === 'clickaway') return;
    setState((prev) => ({ ...prev, open: false }));
  }, []);

  const value = useMemo(
    () => ({ showSnackbar, hideSnackbar }),
    [showSnackbar, hideSnackbar]
  );

  return (
    <SnackbarContext.Provider value={value}>
      {children}
      <Snackbar
        key={state.key}
        open={state.open}
        autoHideDuration={4200}
        onClose={hideSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        slots={{ transition: Slide }}
        slotProps={{ transition: { direction: 'up' } }}
      >
        <Alert
          onClose={hideSnackbar}
          severity={state.severity}
          variant="filled"
          sx={{ minWidth: 280, alignItems: 'center', boxShadow: 6 }}
        >
          {state.message}
        </Alert>
      </Snackbar>
    </SnackbarContext.Provider>
  );
}

export function useSnackbar() {
  const context = useContext(SnackbarContext);
  if (!context) {
    throw new Error('useSnackbar must be used within a SnackbarProvider');
  }
  return context;
}

export default SnackbarContext;
