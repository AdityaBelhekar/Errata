import { StrictMode, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import Overlay from './Overlay';
import { prefersReducedMotion, scroll, tier } from './lib';
import './app.css';

/* three is ~600KB. It is loaded lazily and only when a tier that can use it is
   available, so a visitor on `?nogl=1` — or on hardware that cannot run the
   procession — never downloads an engine that will not be started. L-7 says
   WebGL is enhancement and never structure; this is that law expressed as a
   network request that does not happen. */
const Scene = lazy(() => import('./Scene'));

const level = tier();
document.documentElement.dataset.tier = level;
if (level === 'off') document.documentElement.setAttribute('data-gl', 'off');

/* A procession that resumes halfway through is not a procession. The browser
   restores scroll position on reload by default, which drops a returning
   visitor into Act II with no idea what Act I said. */
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
scrollTo(0, 0);

scroll.start(prefersReducedMotion());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {level !== 'off' && (
      <Suspense fallback={null}>
        <Scene tier={level} />
      </Suspense>
    )}
    <Overlay />
  </StrictMode>
);
