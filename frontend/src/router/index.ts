import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import DecisionPressure from '../views/DecisionPressure.vue'
import WarPeace from '../views/WarPeace.vue'
import TrumpStatements from '../views/TrumpStatements.vue'
import Regression from '../views/Regression.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Dashboard', component: Dashboard },
    { path: '/decision-pressure', name: 'DecisionPressure', component: DecisionPressure },
    { path: '/war-peace', name: 'WarPeace', component: WarPeace },
    { path: '/statements', name: 'TrumpStatements', component: TrumpStatements },
    { path: '/regression', name: 'Regression', component: Regression },
  ]
})

export default router
