/* Metaforge UI Kit — Toast (gold copy-confirmation pill). */
function Toast({ message, visible }) {
  return (
    <div style={toastStyles.host}>
      <div style={{ ...toastStyles.toast, opacity: visible ? 1 : 0 }} role="status">{message}</div>
    </div>
  );
}
const toastStyles = {
  host: { position: 'fixed', bottom: '2rem', left: '50%', transform: 'translateX(-50%)', zIndex: 100, pointerEvents: 'none' },
  toast: { background: 'var(--colour-accent-gold)', color: 'var(--colour-bg-primary)', padding: '0.25rem 1rem', borderRadius: 'var(--hud-radius)', fontFamily: "'Crimson Text', serif", fontSize: '0.9rem', transition: 'opacity 0.2s ease', whiteSpace: 'nowrap' },
};
window.Toast = Toast;
