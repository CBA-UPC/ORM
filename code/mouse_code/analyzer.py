# %%
import re

# %%
suspiciousWords = ['tracking','fp','fingerprint']
eventsToTrack = ['scroll','wheel','mouse','pointer','drag','drop','copy','cut','paste','select','selectionchange']
eventsToTrack += [base + mod for mod in ['enter','move','leave','start','end','out','over'] for base in ['mouse','pointer','drag']]
waysToSendData = ['fetch','xmlhttprequest','xhr','post','ajax','send'] # TODO: Add 'beacon' and 'axios'; maybe add 'track', 'fp' and 'fingerprint'?
nodeDefinitionSearchRange = 100 # Find function definition node idxs this amount before and after only

# %%
def getOccurrenceClosestNodeInNode(nodes, nodeIdx, occurrence):
    closestNodeIdx = nodeIdx
    occurrenceStart = nodes[nodeIdx]['range'][0] + occurrence.start()
    occurrenceEnd = nodes[nodeIdx]['range'][0] + occurrence.end()
    while nodes[nodeIdx]['range'][0] <= occurrenceEnd:
        closestNodeIdx = nodeIdx
        nodeIdx += 1
        while nodes[nodeIdx]['range'][1] < occurrenceStart:
            nodeIdx += 1
            if nodeIdx >= len(nodes):
                return closestNodeIdx
    return closestNodeIdx

# %%
def analyzeFunctionBodyNode(fileContents, nodes, nodeIdx, sourceNodeIdx, nodesFound):
    nodeContents = fileContents[nodes[nodeIdx]['range'][0]:nodes[nodeIdx]['range'][1]].lower()
    occurenceIndexes = []
    nodeRangeStart, nodeRangeEnd = nodes[nodeIdx]['range']
    for wayToSendData in waysToSendData:
        for occurrence in re.finditer(wayToSendData, nodeContents):
            closestNodeIdx = getOccurrenceClosestNodeInNode(nodes, nodeIdx, occurrence)
            if nodes[closestNodeIdx]['type'] == 'Literal':
                raw = nodes[closestNodeIdx]['raw']
                startIdx = raw.lower().index(wayToSendData)
                if startIdx > 1 and not raw[startIdx - 1].isalpha():
                    continue
                if startIdx + len(wayToSendData) < len(raw) - 1 and not raw[startIdx + len(wayToSendData)].isalpha():
                    continue
            elif nodes[closestNodeIdx]['type'] == 'Identifier':
                currentNodeIdx = closestNodeIdx
                if nodes[nodes[currentNodeIdx]['previous']]['type'] == 'MemberExpression' and nodes[nodes[currentNodeIdx]['previous']]['property'] == currentNodeIdx:
                    currentNodeIdx = nodes[currentNodeIdx]['previous']
                if nodes[nodes[currentNodeIdx]['previous']]['type'] != 'CallExpression' or nodes[nodes[currentNodeIdx]['previous']]['callee'] != currentNodeIdx:
                    continue
            else:
                continue
            nodeFoundTuple = (nodes[sourceNodeIdx]['_id'], nodes[closestNodeIdx]['_id'], abs(nodes[sourceNodeIdx]['_id'] - nodes[closestNodeIdx]['_id']))
            if nodeFoundTuple not in nodesFound:
                suspicious = False
                for suspiciousWord in suspiciousWords:
                    if suspiciousWord in nodeContents:
                        suspicious = True
                        break
                nodesFound.append((*nodeFoundTuple, suspicious))
    return False

# %%
def analyzeFunctionDefinitionNodes(fileContents, nodes, nodeIdx, skipIdentifiers, sourceNodeIdx, nodesFound):
    previous = nodes[nodes[nodeIdx]['previous']]
    if previous['type'] == 'MemberExpression':
        if previous['property'] != nodeIdx:
            return False
        nodeIdx = previous['_id']
        previous = nodes[previous['previous']]
    if previous['type'] == 'FunctionDeclaration':
        if analyzeFunctionBodyNode(fileContents, nodes, previous['body'], sourceNodeIdx, nodesFound):
            return True
    elif previous['type'] == 'VariableDeclarator':
        if previous['init'] != None and previous['init'] != nodeIdx:
            if analyzeFunctionNode(fileContents, nodes, previous['init'], skipIdentifiers, sourceNodeIdx, nodesFound):
                return True
    elif previous['type'] == 'AssignmentExpression' or previous['type'] == 'AssignmentPattern':
        if previous['right'] != nodeIdx:
            if analyzeFunctionNode(fileContents, nodes, previous['right'], skipIdentifiers, sourceNodeIdx, nodesFound):
                return True
    elif previous['type'] == 'Property':
        if previous['value'] != None and previous['value'] != nodeIdx:
            if analyzeFunctionNode(fileContents, nodes, previous['value'], skipIdentifiers, sourceNodeIdx, nodesFound):
                return True
    return False

# %%
def analyzeFunctionNode(fileContents, nodes, nodeIdx, skipIdentifiers, sourceNodeIdx, nodesFound):
    if nodes[nodeIdx]['type'] == 'MemberExpression':
        nodeIdx = nodes[nodeIdx]['property']
    if nodes[nodeIdx]['type'] == 'FunctionExpression':
        return analyzeFunctionBodyNode(fileContents, nodes, nodes[nodeIdx]['body'], sourceNodeIdx, nodesFound)
    elif nodes[nodeIdx]['type'] == 'ArrowFunctionExpression':
        body = nodes[nodes[nodeIdx]['body']]
        if body['expression']:
            return False
        return analyzeFunctionBodyNode(fileContents, nodes, nodes[nodeIdx]['body'], sourceNodeIdx, nodesFound)
    elif nodes[nodeIdx]['type'] == 'Identifier' and skipIdentifiers > 0:
        currentNodeIdx = max(0, nodeIdx - nodeDefinitionSearchRange)
        lastNodeIdx = min(nodeIdx + nodeDefinitionSearchRange, len(nodes) - 1)
        while currentNodeIdx <= lastNodeIdx:
            if nodes[currentNodeIdx]['type'] == 'Identifier' and nodes[currentNodeIdx]['name'] == nodes[nodeIdx]['name']:
                if analyzeFunctionDefinitionNodes(fileContents, nodes, currentNodeIdx, skipIdentifiers - 1, sourceNodeIdx, nodesFound):
                    return True
            currentNodeIdx += 1
    return False

# %%
def analyzeNodes(fileContents, nodes, nodesFound, strict):
    for node in nodes:
        if node['type'] == 'Identifier':
            if node['name'] in ['addEventListener', 'attachEvent']:
                calleeId = node['_id']
                previous = nodes[node['previous']]
                if previous['type'] == 'MemberExpression':
                    if previous['property'] != node['_id']:
                        continue
                    calleeId = previous['_id']
                    previous = nodes[previous['previous']]
                if previous['type'] == 'CallExpression':
                    if previous['callee'] != calleeId or len(previous['arguments']) < 2:
                        continue
                    eventArgument = nodes[previous['arguments'][0]]
                    if eventArgument['type'] != 'Literal' and strict:
                        continue
                    if eventArgument['type'] == 'Literal' and eventArgument['raw'][1:-1] not in eventsToTrack:
                        continue
                    if analyzeFunctionNode(fileContents, nodes, previous['arguments'][1], 1, node['_id'], nodesFound):
                        return True
            else:
                for eventToTrack in eventsToTrack:
                    if node['name'] == 'on' + eventToTrack:
                        if analyzeFunctionDefinitionNodes(fileContents, nodes, node['_id'], 1, node['_id'], nodesFound):
                            return True
                        break
                         
    return False

# %%
def analyze(contents, nodes, strict=False):
    try:
        nodesFound = []
        analyzeNodes(contents, nodes, nodesFound, strict)
        return (True, nodesFound)
    except Exception as e:
        return (False, e)
