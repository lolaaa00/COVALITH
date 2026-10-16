import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'Covalith | Collateral Protection',description:'Consensus-backed collateral intelligence and fully funded on-chain protection on GenLayer.'};
export default function Root({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
