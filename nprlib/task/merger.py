import numpy
import logging
import os
log = logging.getLogger("main")

from nprlib.master_task import Task
from nprlib.master_job import Job
from nprlib.utils import (load_node_size, PhyloTree, SeqGroup, generate_id,
                          get_node2content, NPR_TREE_STYLE, NodeStyle, DEBUG,
                          faces)
from nprlib import db
from nprlib.errors import TaskError

__all__ = ["TreeMerger", "select_outgroups"]

class TreeMerger(Task):
    def __init__(self, nodeid, seqtype, task_tree, main_tree, conf):
        # Initialize task
        Task.__init__(self, nodeid, "treemerger", "TreeMerger")
        self.conf = conf
        self.args = conf["tree_splitter"]
        self.task_tree_file = task_tree
        self.main_tree = main_tree
        self.task_tree = None
        self.seqtype = seqtype
        self.rf = None, None # Robinson foulds to orig partition
        self.outgroup_match_dist = 0.0
        self.outgroup_match = ""
        self.pre_iter_support = None # support of the node pre-iteration
        self.init()
        self.pruned_tree = os.path.join(self.taskdir, "pruned_tree.nw")
        
    def finish(self):
        def euc_dist(x, y):
            return len(x.symmetric_difference(y)) / float((len(x) + len(y)))
        
        ttree = PhyloTree(self.task_tree_file)
        mtree = self.main_tree
        ttree.dist = 0

        cladeid, target_seqs, out_seqs = db.get_node_info(self.nodeid)
        self.out_seqs = out_seqs
        self.target_seqs = target_seqs

        ttree_content = ttree.get_node2content()
        if mtree and not out_seqs:
            mtree_content = mtree.get_node2content()
            log.log(28, "Finding best scoring outgroup from previous iteration.")
            #cladeid = generate_id([n.name for n in ttree_content[ttree]])
            #orig_target = mtree.search_nodes(cladeid=cladeid)[0]
            #target_left = set([_n.name for _n in orig_target.children[0]])
            #target_right = set([_n.name for _n in orig_target.children[1]])
            for _n in mtree_content:
                if _n.cladeid == cladeid:
                    orig_target = _n 
            target_left = set([_n.name for _n in mtree_content[orig_target.children[0]]])
            target_right = set([_n.name for _n in mtree_content[orig_target.children[1]]])
                    
            partition_pairs = []
            everything = set([_n.name for _n in ttree_content[ttree]])
            for n, content in ttree_content.iteritems():
                if n is ttree:
                    continue
                left = set([_n.name for _n in content])
                right =  everything - left
                d1 = euc_dist(left, target_left)
                d2 = euc_dist(left, target_right)
                best_match = min(d1, d2)
                partition_pairs.append([best_match, left, right, n])

            partition_pairs.sort()
            
            self.outgroup_match_dist = partition_pairs[0][0]
            #self.outgroup_match = '#'.join( ['|'.join(partition_pairs[0][1]),
            #                      '|'.join(partition_pairs[0][2])] )

            
            outgroup = partition_pairs[0][3]
            ttree.set_outgroup(outgroup)
      
            ttree.dist = orig_target.dist
            ttree.support = orig_target.support

            if DEBUG():
                orig_target.children[0].img_style["fgcolor"] = "orange"
                orig_target.children[0].img_style["size"] = 20
                orig_target.children[1].img_style["fgcolor"] = "orange"
                orig_target.children[1].img_style["size"] = 20
                orig_target.img_style["bgcolor"] = "lightblue"
                
                NPR_TREE_STYLE.title.add_face( faces.TextFace("MainTree: Pre iteration partition", fgcolor="blue"), 0)
                mtree.show(tree_style=NPR_TREE_STYLE)
                NPR_TREE_STYLE.title.clear()

                orig_target.children[0].set_style(None)
                orig_target.children[1].set_style(None)
                orig_target.set_style(None)

            # Merge task and main trees
            parent = orig_target.up
            orig_target.detach()
            parent.add_child(ttree)

            if DEBUG():
                outgroup.img_style["fgcolor"]="Green"
                outgroup.img_style["size"]= 12
                ttree.img_style["bgcolor"] = "lightblue"
                outgroup.add_face(faces.TextFace("DIST=%s" % partition_pairs[0][0]), 0, "branch-top")
                NPR_TREE_STYLE.title.clear()
                NPR_TREE_STYLE.title.add_face(faces.TextFace("Optimized node. Most similar outgroup with previous iteration is shown", fgcolor="blue"), 0)
                ttree.show(tree_style=NPR_TREE_STYLE)

        elif mtree and out_seqs:
            log.log(26, "Rooting tree using %d custom seqs" %
                   len(out_seqs))

            #log.log(22, "Out seqs:    %s", len(out_seqs))
            #log.log(22, "Target seqs: %s", target_seqs)
            if len(out_seqs) > 1:
                outgroup = ttree.get_common_ancestor(out_seqs)
                # if out_seqs are not grouped in a single node
                if outgroup is ttree:
                    # root to target seqs and retry out_seqs
                    target = ttree.get_common_ancestor(target_seqs)
                    ttree.set_outgroup(target)
                    outgroup = ttree.get_common_ancestor(out_seqs)
            else:
                outgroup = ttree & list(out_seqs)[0]

            if outgroup is not ttree:
                ttree.set_outgroup(outgroup)
                
                orig_target = self.main_tree.get_common_ancestor(target_seqs)
                found_target = outgroup.get_sisters()[0]
                
                if DEBUG():
                    for _seq in out_seqs:
                        tar =  ttree & _seq
                        tar.img_style["fgcolor"]="green"
                        tar.img_style["size"] = 12
                        tar.img_style["shape"] = "circle"
                    outgroup.img_style["fgcolor"]="lightgreen"
                    outgroup.img_style["size"]= 12
                    found_target.img_style["bgcolor"] = "lightblue"
                    NPR_TREE_STYLE.title.clear()
                    NPR_TREE_STYLE.title.add_face(faces.TextFace("Optimized node. Outgroup is in green and distance to original partition is shown", fgcolor="blue"), 0)
                    ttree.show(tree_style=NPR_TREE_STYLE)
                    
                ttree = ttree.get_common_ancestor(target_seqs)
                outgroup.detach()
                self.pre_iter_support = orig_target.support
                # Use previous dist and support
                ttree.dist = orig_target.dist
                ttree.support = orig_target.support
                parent = orig_target.up
                orig_target.detach()
                parent.add_child(ttree)
            else:
                raise TaskError("Outgroup was split")
               
        else:
            def sort_outgroups(x,y):
                v = cmp(x.support, y.support)
                if v == 0:
                    v = cmp(n2targetdist[x], n2targetdist[y])
                if v == 0:
                    v = cmp(len(ttree_content[x]), len(ttree_content[y]))
                return v
            
            log.log(28, "Rooting close to midpoint.")
            outgroup = ttree.get_midpoint_outgroup()
            n2rootdist, n2targetdist = distance_matrix(outgroup, leaf_only=False,
                                                       topology_only=True)
            
            valid_nodes = n2targetdist.keys()
            valid_nodes.sort(sort_outgroups)
            best_outgroup = valid_nodes[0]
                                   
            ttree.set_outgroup(best_outgroup)
            self.main_tree = ttree
            orig_target = ttree
            if DEBUG():
                outgroup.img_style["size"] = 20
                outgroup.img_style["fgcolor"] = "green"
                NPR_TREE_STYLE.title.clear()
                NPR_TREE_STYLE.title.add_face(faces.TextFace("First iteration split.Outgroup is in green", fgcolor="blue"), 0)
                ttree.show(tree_style=NPR_TREE_STYLE)

        tn = orig_target.copy()
        self.pre_iter_task_tree = tn
        self.rf = orig_target.robinson_foulds(ttree)
        self.pre_iter_support = orig_target.support

                
        # Reloads node2content of the rooted tree and generate cladeids
        ttree_content = self.main_tree.get_node2content()
        for n, content in ttree_content.iteritems():
            cid = generate_id([_n.name for _n in content])
            n.add_feature("cladeid", cid)

        ttree.write(outfile=self.pruned_tree)
        self.task_tree = ttree
        if DEBUG():
            for _n in self.main_tree.traverse():
                _n.img_style = None
        
    def check(self):
        if os.path.exists(self.pruned_tree):
            return True
        return False

def root_distance_matrix(root):
    n2rdist = {root:0.0}
    for n in root.iter_descendants("preorder"):
        n2rdist[n] = n2rdist[n.up] + n.dist
    return n2rdist

def distance_matrix(target, leaf_only=False, topology_only=False):
    # Detect the root and the target branch
    root = target
    while root.up:
        target_branch = root
        root = root.up
    # Calculate distances to the root
    n2rdist = {root:0.0}        
    for n in root.get_descendants("preorder"):
        dist = 1.0 if topology_only else n.dist
        n2rdist[n] = n2rdist[n.up] + dist

    # Calculate distances to the target node
    n2tdist = {}        
    for n in root.traverse():
        ancestor = root.get_common_ancestor(n, target)
        if not leaf_only or n.is_leaf():
            if ancestor != target:
                n2tdist[n] = n2rdist[target] + n2rdist[n] - n2rdist[ancestor]
    return n2rdist, n2tdist
    
        
def select_outgroups(target, n2content, options):
    """Given a set of target sequences, find the best set of out
    sequences to use. Several ways can be selected to find out
    sequences:
    """
    
    name2dist = {"min": numpy.min, "max": numpy.max,
                 "mean":numpy.mean, "median":numpy.median}
    
    
    policy = options["_outgroup_policy"]
    out_size = options["_outgroup_size"]
    out_distfn = name2dist[options["_outgroup_dist"]]
    topology_only = options["_outgroup_topology_dist"]
    out_min_support = options["_outgroup_min_support"]

    if not target.up:
        raise ValueError("Cannot select outgroups for root node!")
    if not out_size:
        raise ValueError("You are trying to set 0 outgroups!")
    
    if policy == "leaves":
        leaf_only = True
    else:
        leaf_only = False
    n2rootdist, n2targetdist = distance_matrix(target, leaf_only=leaf_only,
                                               topology_only=topology_only)

    max_dist = max(n2targetdist.values())
    # normalize all distances from 0 to 1
    n2normdist = dict([[n, n2targetdist[n]/max_dist] for n in n2targetdist])
    ref_norm_dist = out_distfn(n2normdist.values())
    n2refdist = dict([[n, abs(n2normdist[n] - ref_norm_dist)] for n in n2targetdist])
    n2size = dict([[n, float(len(n2content[n]))] for n in n2targetdist])
    n2sizedist = dict([ [n, (abs(n2size[n]-out_size)/(n2size[n]+out_size))]
                        for n in n2targetdist])
    def sort_by_best(x,y):
        v = cmp(max([n2refdist[x], n2sizedist[x], n.support]),
                max([n2refdist[y], n2sizedist[y], n.support]))
        if v == 0:
            v = cmp(n2sizedist[x], n2sizedist[y])
        if v == 0:
            v = cmp(n2refdist[x], n2refdist[y])
        return v
        
    valid_nodes = [n for n in n2targetdist if n.support >= out_min_support and
                   not n2content[n] & n2content[target]]
    if not valid_nodes:
        log.warning("Outgroup not could not satisfy min branch support")
        valid_nodes = [n for n in n2targetdist if not n2content[n] & n2content[target]]
    valid_nodes.sort(sort_by_best)
    
    if DEBUG():
        for n in valid_nodes[:20]:
            print ''.join(map(lambda x: "% 20s" %x,
                              [n.name, len(n2content[n]), n2refdist[n], n2sizedist[n], n.support,
                               max([n2refdist[n], n2sizedist[n], n.support])]))

    seqs = [n.name for n in n2content[target]]
    if policy == "node":
        outs = [n.name for n in n2content[valid_nodes[0]]]
    elif policy == "leaves":
        outs = [n.name for n in valid_nodes[:out_size]]

    if len(outs) < out_size:
        log.log(28, "Outgroup size not reached.")

    if DEBUG():
        root = target.get_tree_root()
        for _seq in outs:
            tar =  root & _seq
            tar.img_style["fgcolor"]="green"
            tar.img_style["size"] = 12
            tar.img_style["shape"] = "circle"
        target.img_style["bgcolor"] = "lightblue"
        NPR_TREE_STYLE.title.clear()
        NPR_TREE_STYLE.title.add_face( faces.TextFace("MainTree:"
            " Outgroup selection is mark in green.Red=optimized nodes ",
            fgcolor="blue"), 0)
        root.show(tree_style=NPR_TREE_STYLE)
        for _n in root.traverse():
            _n.img_style = None
        
    return set(seqs), set(outs)
      
