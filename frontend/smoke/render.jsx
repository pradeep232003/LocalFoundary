import React from 'react';
import {renderToString} from 'react-dom/server';
import App from '../src/App';
import {AuthProvider} from '../src/AuthContext';
import AgentBuilder from '../src/AgentBuilder';
import CodebaseRagPanel from '../src/panels/CodebaseRagPanel';
import SettingsPanel from '../src/panels/SettingsPanel';
import UserAuthModal from '../src/UserAuthModal';
const noop=()=>{};
const project={id:'test-project',name:'Test app',profile:'starter'};
const config={offline_only:true,providers:{local:{configured:false,model:''}}};
const views=[
 ['App',<AuthProvider><App/></AuthProvider>],
 ['Agent Studio',<AgentBuilder projects={[project]} project={project} config={config} onReturnToAppBuilder={noop}/>],
 ['Source search',<CodebaseRagPanel project={project} id={project.id}/>],
 ['Project settings',<SettingsPanel project={project} config={config}/>],
 ['Unlock',<AuthProvider><UserAuthModal isOpen onClose={noop} onOpenAdminDashboard={noop}/></AuthProvider>],
];
for(const [name,view] of views){const html=renderToString(view);if(!html.length)throw new Error('Empty view: '+name);console.log(name+': rendered');}
