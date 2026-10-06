// Animation is decorative: the console remains usable without it.
let motion;

export function clearMotion() {
  motion?.revert();
  motion = null;
}

export function mountMotion(root, entrance=true) {
  const { gsap, ScrollTrigger } = window;
  if (!gsap || !ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  motion = gsap.matchMedia();
  motion.add('(prefers-reduced-motion: no-preference)', () => {
    const hero = root.querySelectorAll('.workspace-hero h1, .hero-description, .hero-actions');
    if (entrance && hero.length) {
      gsap.from(hero, {
        opacity:0, y:14, duration:.65, stagger:.08, ease:'power2.out', clearProps:'all',
      });
    }
  }, root);
  motion.add('(min-width: 1100px) and (prefers-reduced-motion: no-preference)', () => {
    const section = root.querySelector('.recent-section');
    const aside = root.querySelector('.recent-aside');
    if (!section || !aside) return;
    ScrollTrigger.create({
      trigger:section, pin:aside, pinSpacing:false, start:'top 110px',
      end:() => '+=' + Math.max(1, section.offsetHeight - aside.offsetHeight),
      invalidateOnRefresh:true, anticipatePin:1,
    });
    const cards = [...root.querySelectorAll('.recent-projects .project-card')];
    cards.slice(0,-1).forEach((card,index) => {
      gsap.to(card, {
        y:-10, scale:.985, transformOrigin:'center top', ease:'none',
        scrollTrigger:{trigger:cards[index+1], start:'top 85%', end:'top 45%', scrub:.5},
      });
    });
  }, root);
}
